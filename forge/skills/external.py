"""Recherche et copie des skills externes (T10).

Recherche : catalogues reconnus (catalogs/skills/sources.json) et, si la CLI
gh est authentifiee, recherche de code GitHub. Les resultats sont des
CANDIDATS : rien n'est copie sans approbation explicite, enregistree dans la
configuration (`external_skills`) avec le commit exact examine et l'empreinte
de l'arborescence du skill. Un skill dont l'empreinte a change depuis son
approbation est refuse (erreur bloquante) ; aucun script n'est copie ni execute.
"""
import re
from dataclasses import dataclass, field

from forge.skills import bundle as b
from forge.skills.github import GhCliClient, REPOSITORY
from forge.skills.my_skills import fetch_snapshot, load_skill
from forge.verification.http import FetchError

KEYWORD = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


@dataclass
class Candidate:
    repository: str
    commit: str
    path: str  # dossier parent du skill
    name: str
    description: str
    recognized: bool
    source: str
    score: int
    digest: str = ""
    copied_files: list = field(default_factory=list)
    ignored_files: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def approval(self):
        """Valeur a ajouter a `external_skills` si l'utilisateur approuve ce candidat."""
        return {"repository": self.repository, "commit": self.commit, "path": self.path, "name": self.name,
                "digest": self.digest}

    def as_dict(self):
        return dict(self.__dict__, approval=self.approval())


@dataclass
class SearchResult:
    candidates: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def keywords_for_plan(plan):
    words = {plan.spec.project_type, *plan.resolution.ids()}
    return sorted(w for w in words if KEYWORD.fullmatch(w))


def _score(keywords, name, description):
    text = (name + " " + description).lower()
    return sum(1 for word in keywords if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word), text))


def _candidate(snapshot, base_path, name, client, policy, keywords, recognized, source):
    files = snapshot.entries[name]
    copied = [rel for rel, mode, size in files if b.classify_entry(rel, mode, size, policy) is None]
    ignored = ["%s (%s)" % (rel, b.classify_entry(rel, mode, size, policy)) for rel, mode, size in files if rel not in copied]
    if "SKILL.md" not in copied:
        return None
    meta = b.parse_frontmatter(client.get_text(snapshot.repository, "%s/%s/SKILL.md" % (base_path, name), snapshot.commit))
    description = meta.get("description", "")
    score = _score(keywords, name, description)
    if not score:
        return None
    notes = [] if recognized else ["Source non reconnue : examen manuel complet requis avant approbation"]
    if meta.get("name") != name:
        notes.append("En-tete SKILL.md invalide : sera rejete a la copie")
    digest = snapshot.digest(name)
    if not digest:
        return None  # sans empreinte, l'approbation ne pourrait pas etre controlee
    return Candidate(snapshot.repository, snapshot.commit, base_path, name, description, recognized, source, score,
                     digest, sorted(copied), sorted(ignored), notes)


def _search_catalog(catalog, client, policy, keywords, out):
    snapshot = fetch_snapshot(client, catalog["repository"], catalog["ref"], catalog["path"])
    for name in sorted(snapshot.entries):
        found = _candidate(snapshot, catalog["path"], name, client, policy, keywords, True, catalog["label"])
        if found:
            out.candidates.append(found)


def _search_github(client, policy, keywords, out, known):
    if not isinstance(client, GhCliClient):
        out.notes.append("Recherche de code GitHub NON VERIFIEE : necessite la CLI gh authentifiee")
        return
    items = []
    for word in keywords[:3]:
        items += (client.get_json("/search/code?q=filename:SKILL.md+%s&per_page=5" % word) or {}).get("items", [])
    seen = set()
    for item in items:
        key = ((item.get("repository") or {}).get("full_name"), item.get("path"))
        if key in seen:
            continue
        seen.add(key)
        repository = (item.get("repository") or {}).get("full_name", "")
        parts = item.get("path", "").split("/")
        if not REPOSITORY.fullmatch(repository) or repository in known or len(parts) < 2 or parts[-1] != "SKILL.md":
            continue
        name, base_path = parts[-2], "/".join(parts[:-2]) or "."
        if base_path == "." or not b.SKILL_NAME.fullmatch(name):
            continue
        try:
            snapshot = fetch_snapshot(client, repository, "HEAD", base_path)
            found = name in snapshot.entries and _candidate(
                snapshot, base_path, name, client, policy, keywords, False, "recherche GitHub")
        except FetchError as exc:
            out.notes.append("%s : %s" % (repository, exc))
            continue
        if found:
            out.candidates.append(found)


def search(keywords, client, config):
    """Retourne des candidats tries par pertinence. Aucun fichier n'est copie."""
    policy, out = config["copy"], SearchResult()
    keywords = [k for k in keywords if KEYWORD.fullmatch(k)]
    if not keywords:
        out.notes.append("Aucun mot-cle exploitable")
        return out
    for catalog in config["external_catalogs"]:
        try:
            _search_catalog(catalog, client, policy, keywords, out)
        except FetchError as exc:
            out.notes.append("%s NON VERIFIE : %s" % (catalog["repository"], exc))
    if config["search"]["github_code_search"]:
        known = {c["repository"] for c in config["external_catalogs"]} | {config["my_skills"]["repository"]}
        try:
            _search_github(client, policy, keywords, out, known)
        except FetchError as exc:
            out.notes.append("Recherche GitHub NON VERIFIEE : %s" % exc)
    out.candidates.sort(key=lambda c: (not c.recognized, -c.score, c.repository, c.name))
    del out.candidates[config["search"]["max_candidates"]:]
    return out


MODIFIED = "modifie depuis son approbation (empreinte differente) : examiner puis approuver a nouveau"


def _approved_snapshot(client, repository, commit, path):
    snapshot = fetch_snapshot(client, repository, commit, path)
    if snapshot.commit != commit:
        raise FetchError("Commit different de celui approuve")
    return snapshot


def check_approval(snapshot, name, digest):
    """Retourne None si le skill est intact, sinon la raison du refus."""
    if name not in snapshot.entries:
        return "absent du commit approuve"
    if snapshot.digest(name) != digest:
        return MODIFIED
    return None


def collect_approved(approvals, agents, client, config, result):
    """Copie les skills approuves, au commit et a l'empreinte approuves, avec les memes controles."""
    policy = config["copy"]
    recognized = {c["repository"] for c in config["external_catalogs"]}
    for repository, commit, path, name, digest in approvals:
        source = "%s (approuve%s)" % (repository, "" if repository in recognized else ", source non reconnue")
        try:
            snapshot = _approved_snapshot(client, repository, commit, path)
            problem = check_approval(snapshot, name, digest)
            if problem:
                record = b.SkillRecord(name, source, commit, "absent" if name not in snapshot.entries else "modifie",
                                       notes=[problem])
            else:
                record = load_skill(name, snapshot, client, path, policy)
        except FetchError as exc:
            record = b.SkillRecord(name, source, commit, "NON VERIFIE", notes=[str(exc)])
        record.source = source
        result.records.append(record)
        if record.status == "copie":
            b.place(record, agents, result)
    return result


def verify_approvals(approvals, client):
    """Controle en ligne des approbations (import, reprise) sans rien copier.

    Statuts : PASS (intact), FAIL (absent ou modifie), NON VERIFIE (inaccessible).
    """
    checks = []
    for repository, commit, path, name, digest in approvals:
        item = {"repository": repository, "commit": commit, "path": path, "name": name, "digest": digest}
        try:
            problem = check_approval(_approved_snapshot(client, repository, commit, path), name, digest)
        except FetchError as exc:
            checks.append(dict(item, status="NON VERIFIE", message=str(exc)))
            continue
        checks.append(dict(item, status="FAIL" if problem else "PASS", message=problem or "Empreinte identique"))
    return checks

