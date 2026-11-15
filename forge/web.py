"""Cas d'usage exposes a l'interface locale, independants du transport HTTP.

Chaque fonction retourne (statut HTTP, corps en octets, type de contenu, nom de
telechargement ou None), dans l'ordre attendu par server.Handler.reply.
Toute entree est revalidee ici : le navigateur n'est jamais une source de
confiance. Le reseau n'est utilise que si `verify` ou `skills` est demande,
ou par la recherche / verification explicite des skills externes.
"""
import json

from forge import diagnostics as d
from forge.config.answers import envelope, parse_answers, unwrap
from forge.config.catalog import load_catalog
from forge.config.profiles import PROFILE_FIELDS, ProfileNotFound, ProfileStore, load_predefined
from forge.config.spec import AGENTS, OPTIONS, PROJECT_TYPES, SECURITY_LEVELS, SpecError, parse_approvals
from forge.diagnostics import ForgeError
from forge.generator.archive import build_zip
from forge.generator.context import AGENT_INFO, PROJECT_TYPE_LABELS
from forge.mcp.catalog import load_mcp_catalog
from forge.pipeline import run
from forge.planner.plan import build_plan
from forge.skills import service as skill_service

JSON = "application/json; charset=utf-8"
REQUEST_FIELDS = {"config", "verify", "skills"}


def _json(status, payload):
    return status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), JSON, None


def catalog_payload():
    catalog = load_catalog()
    technologies = [
        {
            "id": t.id, "name": t.name, "category": t.category, "description": t.description, "docs": t.docs,
            "package": t.package, "versions": list(t.supported_versions), "preferred": t.preferred_version,
            "requires": [list(options) for options in t.requires], "conflicts": list(t.conflicts),
        }
        for t in catalog.technologies.values()
    ]
    categories = [{"id": c.id, "label": c.label, "min": c.min, "max": c.max} for c in catalog.categories.values()]
    return _json(200, {
        "categories": categories,
        "technologies": technologies,
        "agents": [{"id": a, "name": AGENT_INFO[a]["name"]} for a in AGENTS],
        "project_types": [{"id": p, "label": PROJECT_TYPE_LABELS[p]} for p in PROJECT_TYPES],
        "security_levels": list(SECURITY_LEVELS),
        "options": sorted(OPTIONS),
        "mcp_servers": [_mcp_payload(server) for server in load_mcp_catalog().values()],
    })


def _mcp_payload(server):
    transport = server.transport
    return {
        "id": server.id, "name": server.name, "need": server.need, "reason": server.reason,
        "project_types": list(server.project_types), "registry_name": server.registry_name,
        "repository": server.repository, "license": server.license, "docs": server.docs,
        "permissions": list(server.permissions), "token_env": server.token_env, "runtime": server.runtime,
        "transport": transport["url"] if transport["type"] == "http" else " ".join([transport["command"], *transport["args"]]),
    }


def _parse_request(raw):
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError("JSON invalide") from exc
    if not isinstance(body, dict) or set(body) - REQUEST_FIELDS or "config" not in body:
        raise SpecError("Requete invalide : champs config, verify, skills")
    verify, skills = body.get("verify", False), body.get("skills", False)
    if not isinstance(verify, bool) or not isinstance(skills, bool):
        raise SpecError("verify et skills doivent etre booleens")
    return body["config"], verify, skills


def _execute(raw):
    config, verify, skills = _parse_request(raw)
    return run(config, verify=verify, skills=skills)


def _failure(exc):
    if isinstance(exc, ForgeError):
        return _json(422, {"ok": False, "error": str(exc), "diagnostics": [x.as_dict() for x in exc.diagnostics]})
    return _json(400, {"ok": False, "error": str(exc), "diagnostics": []})


def plan_payload(raw):
    """Apercu : diagnostics, rapports et contenu des fichiers (aucune ecriture)."""
    try:
        result = _execute(raw)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    payload = result.as_dict()
    payload["contents"] = result.files
    return _json(200, payload)


def archive_payload(raw):
    """Repete tous les controles avant de produire l'archive ; refuse toute erreur."""
    try:
        result = _execute(raw)
        if d.has_errors(result.diagnostics):
            raise ForgeError("Erreurs bloquantes", [x for x in result.diagnostics if x.severity is d.Severity.ERROR])
        name = result.plan.spec.name
        content = build_zip(name, result.files)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    return 200, content, "application/zip", name + ".zip"


# --- Reponses (brouillon, import) et profils (T05) ---------------------------
def _body(raw, fields):
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON invalide : le fichier ou la requete n'est pas un JSON valide") from exc
    if not isinstance(body, dict) or set(body) != fields:
        raise ValueError("Requete invalide : champs attendus " + ", ".join(sorted(fields)))
    return body


def answers_validate_payload(raw):
    """Valide un export JSON ou un brouillon ; retourne les reponses normalisees."""
    try:
        document = _body(raw, {"document"})["document"]
        normalised = parse_answers(unwrap(document), load_catalog())
    except ValueError as exc:
        return _json(400, {"ok": False, "error": str(exc)})
    return _json(200, {"ok": True, "answers": normalised, "export": envelope(normalised)})


def _store(catalog):
    predefined = load_predefined(catalog)
    return predefined, ProfileStore(catalog, reserved={p["id"] for p in predefined})


def _profile_call(action):
    try:
        return action()
    except ProfileNotFound as exc:
        return _json(404, {"ok": False, "error": str(exc)})
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Ecriture du fichier de profils impossible"
        return _json(400 if isinstance(exc, ValueError) else 500, {"ok": False, "error": message})


def profiles_payload():
    def action():
        predefined, store = _store(load_catalog())
        return _json(200, {"ok": True, "predefined": predefined, "custom": store.list(), "storage": str(store.path)})
    return _profile_call(action)


def profile_create_payload(raw):
    def action():
        _, store = _store(load_catalog())
        return _json(201, {"ok": True, "profile": store.create(_body(raw, PROFILE_FIELDS))})
    return _profile_call(action)


def profile_update_payload(profile_id, raw):
    def action():
        _, store = _store(load_catalog())
        return _json(200, {"ok": True, "profile": store.update(profile_id, _body(raw, PROFILE_FIELDS))})
    return _profile_call(action)


def profile_delete_payload(profile_id):
    def action():
        _, store = _store(load_catalog())
        store.delete(profile_id)
        return _json(200, {"ok": True})
    return _profile_call(action)


# --- Skills externes (T10) : recherche et verification explicites ----------
def skills_search_payload(raw):
    """Candidats pour la configuration courante ; rien n'est copie ni execute."""
    try:
        plan = build_plan(_body(raw, {"config"})["config"])
        if not plan.ok:
            raise ForgeError("Configuration incomplete : recherche impossible",
                             [x for x in plan.diagnostics if x.severity is d.Severity.ERROR])
        found = skill_service.search_for_plan(plan)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    return _json(200, {"ok": True, "candidates": [c.as_dict() for c in found.candidates], "notes": found.notes})


def skills_verify_payload(raw):
    """Revalide des approbations (import, profil, brouillon) contre GitHub, sans copie."""
    try:
        approvals = parse_approvals(_body(raw, {"approvals"})["approvals"])
        checks = skill_service.verify_approvals(approvals)
    except ValueError as exc:
        return _failure(exc)
    return _json(200, {"ok": all(c["status"] == "PASS" for c in checks), "checks": checks})
