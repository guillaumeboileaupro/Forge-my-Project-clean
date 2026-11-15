"""Controles du contenu modifie par l'utilisateur (editeur T16, fusion T17).

Les textes regeneres par le moteur sont la reference. Une modification est
refusee si elle introduit un secret, change la semantique d'une configuration
qui fait executer des commandes ou contacter des serveurs (MCP, hooks d'agents),
modifie un script de hook, renomme un skill, ou si un chemin final est sensible.
"""
import json
import re
import tomllib

from forge.generator.archive import EXECUTABLE_PREFIXES

# Jetons a format reconnaissable (prefixe fixe) : faible taux de faux positifs.
SECRET_PATTERNS = [
    ("jeton GitHub", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("cle d'acces AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("cle privee", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("jeton Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("cle d'API Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("cle Stripe", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{16,}\b")),
    ("cle d'API (sk-)", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("jeton npm", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    # Affectation litterale d'un secret ; une reference ${VAR} ou $VAR n'est pas un secret.
    ("affectation de secret", re.compile(
        r"(?i)\b(pass(?:word|wd)?|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b"
        r"[\"']?\s*[:=]\s*[\"']([^\"'\s$<>{}]{8,})[\"']")),
]
# Configurations qui declenchent des commandes ou des connexions : semantique figee.
JSON_LOCKED = {".mcp.json", ".claude/settings.json", ".codex/hooks.json", ".github/hooks/forge-guard.json"}
TOML_LOCKED = {".codex/config.toml"}
SKILL_DIRS = (".claude/skills/", ".agents/skills/")
SENSITIVE = re.compile(
    r"(^|/)(\.git|\.ssh|\.gnupg|\.aws)(/|$)|(^|/)\.env(\.(?!example$)[\w.-]+)?$"
    r"|(^|/)id_(rsa|dsa|ecdsa|ed25519)$|\.(pem|key|p12|pfx|keystore|jks)$|(^|/)\.(npmrc|pypirc|netrc)$")
FRONTMATTER_NAME = re.compile(r"\A---\s*\n(?:.*\n)*?name:\s*[\"']?([^\"'\n]+?)[\"']?\s*\n(?:.*\n)*?---", re.M)


class ContentError(ValueError):
    """Contenu modifie refuse ; chaque probleme est decrit pour l'utilisateur."""

    def __init__(self, problems):
        super().__init__("Contenu refuse : " + " ; ".join(problems))
        self.problems = problems


def find_secrets(text):
    found = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            found.append(label)
    return found


def _same_json(original, edited):
    try:
        return json.loads(original) == json.loads(edited)
    except ValueError:
        return False


def _same_toml(original, edited):
    try:
        return tomllib.loads(original) == tomllib.loads(edited)
    except tomllib.TOMLDecodeError:
        return False


def _skill_name(text):
    match = FRONTMATTER_NAME.match(text)
    return match.group(1).strip() if match else None


def check_modified(path, generated, edited):
    """Problemes d'une modification de path (liste vide si acceptee)."""
    problems = ["%s : %s detecte(e)" % (path, label) for label in find_secrets(edited)]
    if path in JSON_LOCKED and not _same_json(generated, edited):
        problems.append("%s : configuration MCP ou hooks d'agents modifiee (seule la mise en forme peut changer)" % path)
    if path in TOML_LOCKED and not _same_toml(generated, edited):
        problems.append("%s : configuration MCP Codex modifiee (seule la mise en forme peut changer)" % path)
    if path.startswith(EXECUTABLE_PREFIXES) and edited != generated:
        problems.append("%s : script de hook modifie (non modifiable depuis l'editeur)" % path)
    if path.startswith(SKILL_DIRS) and path.endswith("/SKILL.md") and _skill_name(edited) != _skill_name(generated):
        problems.append("%s : nom du skill absent ou modifie dans l'en-tete" % path)
    return problems


def check_paths(paths):
    return ["%s : chemin sensible interdit" % path for path in sorted(paths) if SENSITIVE.search(path)]


def check_contents(generated, final):
    """Valide final (chemin -> texte) par rapport a generated ; leve ContentError."""
    problems = check_paths(final)
    for path in sorted(final):
        if final[path] != generated.get(path):
            problems.extend(check_modified(path, generated.get(path, ""), final[path]))
    if problems:
        raise ContentError(problems)
