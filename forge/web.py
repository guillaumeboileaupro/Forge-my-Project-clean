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
from forge.filesystem import workflow
from forge.filesystem.destination import browse
from forge.filesystem.preview import validate_preview
from forge.filesystem.writer import StaleError, WriteFailure
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


def _parse_request(raw, extra=()):
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError("JSON invalide") from exc
    allowed = REQUEST_FIELDS | set(extra)
    if not isinstance(body, dict) or set(body) - allowed or "config" not in body:
        raise SpecError("Requete invalide : champs " + ", ".join(["config", "verify", "skills", *extra]))
    verify, skills = body.get("verify", False), body.get("skills", False)
    if not isinstance(verify, bool) or not isinstance(skills, bool):
        raise SpecError("verify et skills doivent etre booleens")
    return body


def _execute(raw, extra=()):
    """Regenere le plan (controles repetes) ; retourne le resultat et la requete decodee."""
    body = _parse_request(raw, extra)
    return run(body["config"], verify=body.get("verify", False), skills=body.get("skills", False)), body


def _validated_files(raw, extra):
    """Plan sans erreur bloquante + editions revalidees (chemins, tailles, contenu)."""
    result, body = _execute(raw, ("files", *extra))
    if d.has_errors(result.diagnostics):
        raise ForgeError("Erreurs bloquantes", [x for x in result.diagnostics if x.severity is d.Severity.ERROR])
    if "files" not in body:
        raise ValueError("Le champ files est requis")
    return result, body, validate_preview(body["files"], result.files)


def _failure(exc):
    if isinstance(exc, ForgeError):
        return _json(422, {"ok": False, "error": str(exc), "diagnostics": [x.as_dict() for x in exc.diagnostics]})
    return _json(400, {"ok": False, "error": str(exc), "diagnostics": []})


def plan_payload(raw):
    """Apercu : diagnostics, rapports et contenu des fichiers (aucune ecriture)."""
    try:
        result, _ = _execute(raw)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    payload = result.as_dict()
    payload["contents"] = result.files
    if result.plan is not None:
        # Suggestion des regles locales, reprise et modifiable dans le formulaire.
        payload["architecture"] = {"source": result.plan.architecture["source"],
                                   "suggested": list(result.plan.architecture["suggested"])}
    return _json(200, payload)


def archive_payload(raw):
    """Repete tous les controles avant de produire l'archive ; refuse toute erreur."""
    try:
        result, body = _execute(raw, ("files",))
        if d.has_errors(result.diagnostics):
            raise ForgeError("Erreurs bloquantes", [x for x in result.diagnostics if x.severity is d.Severity.ERROR])
        files = result.files if body.get("files") is None else validate_preview(body["files"], result.files)
        name = result.plan.spec.name
        content = build_zip(name, files)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    return 200, content, "application/zip", name + ".zip"


def preview_validate_payload(raw):
    """Regenere le plan puis valide l'ensemble exact des textes edites."""
    try:
        result, body = _execute(raw, ("files",))
        if body.get("files") is None:
            raise ValueError("Le champ files est requis pour valider l'apercu")
        files = validate_preview(body["files"], result.files)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    changed = sorted(path for path, content in files.items() if content != result.files[path])
    return _json(200, {"ok": True, "files": sorted(files), "modified": changed})


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


# --- Destination locale, comparaison et ecriture confirmee (T17) -------------
def destination_browse_payload(raw):
    """Sous-dossiers d'un dossier de la racine autorisee (lecture seule)."""
    try:
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON invalide") from exc
        if not isinstance(body, dict) or set(body) - {"path"}:
            raise ValueError("Requete invalide : champ path optionnel uniquement")
        path = body.get("path")
        if path is not None and not isinstance(path, str):
            raise ValueError("path doit etre une chaine")
        listing = browse(path)
    except (ValueError, OSError) as exc:
        return _failure(exc if isinstance(exc, ValueError) else ValueError("Dossier inaccessible : %s" % exc.strerror))
    return _json(200, dict(listing, ok=True))


def write_compare_payload(raw):
    """Regenere, revalide les editions puis compare a la destination ; aucune ecriture."""
    try:
        result, body, files = _validated_files(raw, ("destination",))
        comparison = workflow.compare_destination(body.get("destination"), files)
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    except OSError as exc:
        return _failure(ValueError("Destination inaccessible : %s" % exc.strerror))
    return _json(200, dict(comparison, ok=True, diagnostics=[x.as_dict() for x in result.diagnostics]))


def _journal(report, result):
    """Journal final exige par la specification : genere, ignore, non verifie, echec."""
    operations = report["operations"]
    checks = result.verification.as_dict()["checks"] if result.verification is not None else []
    return {
        "genere": [op["path"] for op in operations if op["action"] in ("created", "replaced", "merged")],
        "ignore": [op["path"] for op in operations if op["action"] in ("kept", "identical")],
        "non_verifie": [x.message for x in result.diagnostics if x.severity is d.Severity.WARNING]
                       # Packages et runtimes NON VERIFIES sont deja des avertissements ; seules les API s'ajoutent.
                       + ["%s %s : %s" % (c["kind"], c["subject"], c["message"]) for c in checks
                          if c["status"] == "NON VERIFIE" and c["kind"] == "api"],
        "echec": [],  # un echec bloque l'ecriture (409, 422 ou 500 avec restauration)
    }


def write_apply_payload(raw):
    """Repete generation, controles, validation et comparaison, puis ecrit apres confirmation."""
    try:
        result, body, files = _validated_files(raw, ("destination", "token", "decisions", "confirm"))
        report = workflow.write_destination(body.get("destination"), files, result.files, body.get("token"),
                                            body.get("decisions", {}), body.get("confirm"))
    except (workflow.StaleValidation, StaleError) as exc:
        return _json(409, {"ok": False, "error": str(exc), "stale": True,
                           "report": getattr(exc, "report", None), "diagnostics": []})
    except WriteFailure as exc:
        return _json(500, {"ok": False, "error": str(exc), "report": exc.report, "diagnostics": []})
    except (ForgeError, ValueError) as exc:
        return _failure(exc)
    except OSError as exc:
        return _failure(ValueError("Destination inaccessible : %s" % exc.strerror))
    report["journal"] = _journal(report, result)
    return _json(200, {"ok": True, "report": report, "diagnostics": [x.as_dict() for x in result.diagnostics]})

