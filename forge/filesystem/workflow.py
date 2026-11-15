"""Comparaison puis ecriture confirmee dans une destination locale (T17).

Independant du transport HTTP : recoit les fichiers deja regeneres et valides.
La comparaison renvoie un jeton HMAC lie a la destination, aux contenus prepares
et a l'etat de chaque cible ; l'ecriture exige ce jeton, sinon la validation est
perimee (configuration, editions ou destination modifiees depuis).
"""
import hashlib
import hmac
import json
import secrets

from forge.filesystem.compare import MAX_MERGEABLE, compare, sha256
from forge.filesystem.content import ContentError, check_modified, check_paths
from forge.filesystem.destination import Destination
from forge.filesystem.writer import apply_changes

ACTIONS = ("keep", "replace", "merge")
_KEY = secrets.token_bytes(32)  # propre au processus : un jeton ne survit pas a un redemarrage


class DecisionError(ValueError):
    """Decision de fusion manquante, inconnue ou invalide."""


class StaleValidation(RuntimeError):
    """Jeton absent ou different : comparer a nouveau avant d'ecrire."""


def _token(destination, files, states):
    material = json.dumps({"destination": destination.path, "files": {p: sha256(c.encode("utf-8")) for p, c in files.items()},
                           "states": states}, sort_keys=True).encode("utf-8")
    return hmac.new(_KEY, material, hashlib.sha256).hexdigest()


def _scan(destination, files):
    with destination.open() as fd:
        return compare(fd, files)


def compare_destination(value, files):
    """Destination decrite, entrees comparees, resume et jeton de validation."""
    destination = Destination(value)
    info = destination.describe()
    entries, states = _scan(destination, files)
    summary = {status: sum(1 for e in entries if e["status"] == status) for status in ("new", "identical", "conflict", "blocked")}
    return {"destination": info, "entries": entries, "summary": summary, "token": _token(destination, files, states)}


def _decisions(entries, decisions, generated):
    if not isinstance(decisions, dict):
        raise DecisionError("decisions : objet chemin -> {action, content} attendu")
    by_path = {e["path"]: e for e in entries}
    conflicts = {p for p, e in by_path.items() if e["status"] == "conflict"}
    unknown = sorted(set(decisions) - conflicts)
    if unknown:
        raise DecisionError("Decision pour un fichier sans conflit : " + ", ".join(unknown))
    missing = sorted(conflicts - set(decisions))
    if missing:
        raise DecisionError("Choisir conserver, remplacer ou fusionner pour : " + ", ".join(missing))
    chosen, problems = {}, []
    for path in sorted(conflicts):
        item = decisions[path]
        if not isinstance(item, dict) or item.get("action") not in ACTIONS or set(item) - {"action", "content"}:
            raise DecisionError("Decision invalide pour %s (keep, replace ou merge)" % path)
        if item["action"] == "merge":
            content = item.get("content")
            if not by_path[path]["mergeable"]:
                raise DecisionError("Fusion impossible pour %s : conserver ou remplacer" % path)
            if not isinstance(content, str) or "\x00" in content or len(content.encode("utf-8", "replace")) > MAX_MERGEABLE:
                raise DecisionError("Contenu fusionne invalide pour %s" % path)
            problems.extend(check_modified(path, generated[path], content))
        elif "content" in item:
            raise DecisionError("content n'est accepte que pour merge (%s)" % path)
        chosen[path] = item
    if problems:
        raise ContentError(problems)
    return chosen


def write_destination(value, files, generated, token, decisions, confirm):
    """Ecrit apres confirmation ; rapport detaille (crees, remplaces, fusionnes, conserves, identiques)."""
    if confirm is not True:
        raise DecisionError("Confirmation explicite requise avant l'ecriture")
    destination = Destination(value)
    if not destination.describe()["writable"]:
        raise DecisionError("Permissions insuffisantes : ecriture impossible dans %s" % destination.path)
    entries, states = _scan(destination, files)
    if not isinstance(token, str) or not hmac.compare_digest(token, _token(destination, files, states)):
        raise StaleValidation("Validation perimee : la destination, la configuration ou les fichiers ont change. "
                              "Comparer a nouveau avant d'ecrire.")
    blocked = [e["path"] for e in entries if e["status"] == "blocked"]
    if blocked:
        raise DecisionError("Ecriture refusee, entrees non sures dans la destination : " + ", ".join(blocked))
    problems = check_paths(files)
    if problems:
        raise ContentError(problems)
    chosen = _decisions(entries, decisions, generated)
    writes, skipped = {}, []
    for entry in entries:
        path, status = entry["path"], entry["status"]
        if status == "new":
            writes[path] = ("create", files[path].encode("utf-8"))
        elif status == "identical":
            skipped.append({"path": path, "action": "identical"})
        else:
            item = chosen[path]
            if item["action"] == "keep":
                skipped.append({"path": path, "action": "kept"})
            else:
                text = item["content"] if item["action"] == "merge" else files[path]
                writes[path] = (item["action"], text.encode("utf-8"))
    report = apply_changes(destination, writes, states)
    report["operations"] = sorted(report["operations"] + skipped, key=lambda op: op["path"])
    report["summary"] = {action: sum(1 for op in report["operations"] if op["action"] == action)
                         for action in ("created", "replaced", "merged", "kept", "identical")}
    return report
