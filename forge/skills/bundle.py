"""Validation du contenu d'un skill et copie vers les dossiers des agents.

Commun aux skills de my-skills (T09) et aux skills externes approuves (T10).
Seuls des fichiers texte d'extensions autorisees sont copies ; scripts,
binaires, liens et executables sont ignores et signales. Rien n'est execute.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from forge import CATALOGS_DIR, TEMPLATES_DIR
from forge import diagnostics as d
from forge.generator.paths import PathError, safe_relative_path
from forge.generator.template import render

SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
AGENT_SKILL_DIRS = {"codex": ".agents/skills", "claude": ".claude/skills"}
# Metadonnees propres a un agent (ex. agents/openai.yaml pour Codex).
AGENT_ONLY_PREFIXES = {"claude": ("agents/",)}
SUSPICIOUS = re.compile(r"(curl|wget)[^\n|]*\|\s*(ba|z)?sh\b|\brm\s+-rf\s+[/~]|base64\s+(-d|--decode)[^\n]*\|", re.I)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_copy_policy(path=None):
    data = json.loads((path or CATALOGS_DIR / "skills" / "sources.json").read_text(encoding="utf-8"))
    return data


def git_blob_sha(content):
    """SHA-1 d'un blob Git : permet de verifier un contenu telecharge contre l'arborescence."""
    data = content.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def tree_digest(entries):
    """Empreinte d'un skill : chemin, mode et blob Git de chaque fichier (copie ou non).

    `entries` : iterable de (chemin relatif, mode, sha du blob). Toute modification,
    ajout ou suppression de fichier dans le dossier du skill change l'empreinte.
    Retourne None si un blob est inconnu (empreinte impossible).
    """
    lines = []
    for rel, mode, sha in sorted(entries):
        if not sha or not re.fullmatch(r"[0-9a-f]{40}", sha):
            return None
        lines.append("%s %s %s\n" % (mode, sha, rel))
    return "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


@dataclass
class SkillRecord:
    name: str
    source: str
    commit: str
    status: str  # copie | absent | rejete | modifie | NON VERIFIE
    files: dict = field(default_factory=dict)  # chemin relatif dans le skill -> contenu
    notes: list = field(default_factory=list)


@dataclass
class SkillBundle:
    records: list = field(default_factory=list)
    files: dict = field(default_factory=dict)  # chemin final -> contenu
    diagnostics: list = field(default_factory=list)


def parse_frontmatter(text):
    """Extrait name/description d'un SKILL.md (cles simples sur une ligne)."""
    match = FRONTMATTER.match(text.replace("\r\n", "\n"))
    if not match:
        return {}
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("name", "description"):
            meta[key.strip()] = value.strip().strip("\"'")
    return meta


def classify_entry(rel_path, mode, size, policy):
    """Retourne None si le fichier est copiable, sinon la raison de l'exclusion."""
    try:
        safe_relative_path(rel_path)
    except PathError:
        return "chemin refuse"
    if mode != "100644":
        return "lien symbolique ou executable"
    if PurePosixPath(rel_path).suffix.lower() not in policy["extensions"]:
        return "type de fichier non copie (script ou binaire possible)"
    if size is None or size > policy["max_file_bytes"]:
        return "fichier trop volumineux"
    return None


def validate_skill(record):
    """Controle SKILL.md et le contenu ; retourne False si le skill est rejete."""
    skill_md = record.files.get("SKILL.md")
    if skill_md is None:
        record.notes.append("SKILL.md absent : skill rejete")
        return False
    meta = parse_frontmatter(skill_md)
    if meta.get("name") != record.name or not meta.get("description"):
        record.notes.append("En-tete SKILL.md invalide (name/description) : skill rejete")
        return False
    for path, content in sorted(record.files.items()):
        if SUSPICIOUS.search(content):
            record.notes.append("%s : commande potentiellement dangereuse a relire avant usage" % path)
    return True


def place(record, agents, bundle):
    """Copie les fichiers d'un skill valide pour chaque agent qui supporte les skills."""
    for agent in (a for a in agents if a in AGENT_SKILL_DIRS):
        skipped = AGENT_ONLY_PREFIXES.get(agent, ())
        for rel, content in sorted(record.files.items()):
            if not rel.startswith(skipped):
                path = "%s/%s/%s" % (AGENT_SKILL_DIRS[agent], record.name, rel)
                bundle.files[path] = content if content.endswith("\n") else content + "\n"


def provenance_document(bundle, agents):
    destinations = ", ".join(AGENT_SKILL_DIRS[a] for a in agents if a in AGENT_SKILL_DIRS) or "aucune"
    records = [
        {"name": r.name, "source": r.source, "commit": r.commit[:12] if r.commit else "-", "status": r.status,
         "destinations": destinations if r.status == "copie" else "-", "notes": list(r.notes)}
        for r in bundle.records
    ]
    template = (TEMPLATES_DIR / "skills" / "SKILLS.md.tmpl").read_text(encoding="utf-8")
    return render(template, {"records": records})


def record_diagnostics(record):
    if record.status == "modifie":  # integrite de l'approbation rompue : blocage
        return [d.error("skill-modified", "Skill %s refuse : %s" % (record.name, "; ".join(record.notes)), record.name)]
    if record.status == "absent":
        return [d.warning("skill-missing", "Skill %s introuvable dans %s" % (record.name, record.source), record.name)]
    if record.status == "rejete":
        return [d.warning("skill-rejected", "Skill %s rejete : %s" % (record.name, "; ".join(record.notes)), record.name)]
    if record.status == "NON VERIFIE":
        return [d.warning("skill-unverified", "Skill %s non recupere : %s" % (record.name, "; ".join(record.notes)), record.name)]
    return [d.warning("skill-review", "Skill %s : %s" % (record.name, n), record.name) for n in record.notes
            if "dangereuse" in n]
