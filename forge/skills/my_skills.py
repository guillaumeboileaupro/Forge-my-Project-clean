"""Selection et recuperation des skills du depot my-skills (T09).

Les skills retenus sont ceux recommandes par les regles locales (selection
deterministe). Le depot est lu a un commit precis (provenance), en lecture
seule ; seuls des fichiers texte sont copies.
"""
from dataclasses import dataclass, field

from forge.skills import bundle as b
from forge.skills.github import SHA, check_repository
from forge.verification.http import FetchError


@dataclass(frozen=True)
class Snapshot:
    repository: str
    commit: str
    entries: dict  # nom du skill -> liste de (chemin relatif, mode, taille)
    blobs: dict = field(default_factory=dict)  # nom du skill -> {chemin relatif: sha du blob}

    def digest(self, name):
        """Empreinte de l'arborescence du skill a ce commit (None si incalculable)."""
        modes = {rel: mode for rel, mode, _ in self.entries.get(name, ())}
        shas = self.blobs.get(name, {})
        return b.tree_digest((rel, mode, shas.get(rel)) for rel, mode in modes.items()) if modes else None


def fetch_snapshot(client, repository, ref, base_path):
    check_repository(repository, ref)
    commit = (client.get_json("/repos/%s/commits/%s" % (repository, ref)) or {}).get("sha", "")
    if not SHA.fullmatch(commit):
        raise FetchError("Commit introuvable pour " + ref)
    tree = client.get_json("/repos/%s/git/trees/%s?recursive=1" % (repository, commit)) or {}
    if tree.get("truncated"):
        raise FetchError("Arborescence tronquee par l'API GitHub")
    prefix = base_path.strip("/") + "/"
    entries, blobs = {}, {}
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or not path.startswith(prefix):
            continue
        name, _, rel = path[len(prefix):].partition("/")
        if b.SKILL_NAME.fullmatch(name) and rel:
            entries.setdefault(name, []).append((rel, item.get("mode"), item.get("size")))
            blobs.setdefault(name, {})[rel] = item.get("sha")
    return Snapshot(repository, commit, entries, blobs)


def load_skill(name, snapshot, client, base_path, policy, status="copie"):
    """Telecharge les fichiers copiables d'un skill (jamais les scripts) et le valide."""
    record = b.SkillRecord(name, snapshot.repository, snapshot.commit, status)
    total = 0
    for rel, mode, size in sorted(snapshot.entries[name]):
        reason = b.classify_entry(rel, mode, size, policy)
        if reason is None and total + size > policy["max_skill_bytes"]:
            reason = "taille totale du skill depassee"
        if reason:
            record.notes.append("%s ignore : %s" % (rel, reason))
            continue
        content = client.get_text(snapshot.repository, "%s/%s/%s" % (base_path, name, rel), snapshot.commit)
        expected = snapshot.blobs.get(name, {}).get(rel)
        if expected and b.git_blob_sha(content) != expected:
            record.notes.append("%s : contenu recu different du blob %s du commit : skill rejete" % (rel, expected[:12]))
            record.status, record.files = "modifie", {}
            return record
        record.files[rel] = content
        total += size
    if not b.validate_skill(record):
        record.status, record.files = "rejete", {}
    return record


def collect_skills(names, agents, client, config, result):
    """Ajoute a `result` les skills my-skills demandes ; indisponibilite = avertissement."""
    source, policy = config["my_skills"], config["copy"]
    if not names:
        return result
    try:
        snapshot = fetch_snapshot(client, source["repository"], source["ref"], source["path"])
    except FetchError as exc:
        for name in names:
            result.records.append(b.SkillRecord(name, source["repository"], "", "NON VERIFIE", notes=[str(exc)]))
        return result
    for name in names:
        if name not in snapshot.entries:
            result.records.append(b.SkillRecord(name, source["repository"], snapshot.commit, "absent"))
            continue
        try:
            record = load_skill(name, snapshot, client, source["path"], policy)
        except FetchError as exc:
            record = b.SkillRecord(name, source["repository"], snapshot.commit, "NON VERIFIE", notes=[str(exc)])
        result.records.append(record)
        if record.status == "copie":
            b.place(record, agents, result)
    return result
