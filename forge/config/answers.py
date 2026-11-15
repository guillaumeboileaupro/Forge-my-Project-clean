"""Reponses du questionnaire, eventuellement incompletes (brouillon, import, profil).

Le format reprend les champs du schema moteur v1 mais tolere une saisie en
cours (nom vide ou partiel, aucun agent, aucune technologie). Il refuse en
revanche tout ce que le formulaire ne peut pas representer : champ inconnu,
type invalide, technologie absente du catalogue, prerequis manquant, conflit,
version non supportee. Les donnees ne sont jamais executees ni interpretees.
"""
import re

from forge.config import spec as s
from forge.rules.compatibility import resolve

FORMAT = "forge-my-project/answers"
SCHEMA_VERSION = 1
PARTIAL_NAME = re.compile(r"^[a-z0-9-]{0,50}$")
FIELDS = s.FIELDS - {"schema_version"}
# Diagnostics acceptables pour un brouillon : ils relevent de la completude.
TOLERATED = {"category-min", "unknown-command"}


class AnswersError(ValueError):
    pass


def _ids(data, key, limit):
    try:
        return list(s._unique_ids(data, key, s.TECH_ID, limit))
    except s.SpecError as exc:
        raise AnswersError(str(exc)) from exc


def unwrap(document):
    """Accepte une enveloppe d'export {format, schema_version, answers} ou des reponses nues."""
    if not isinstance(document, dict):
        raise AnswersError("Objet JSON attendu")
    if "format" in document or "answers" in document:
        if document.get("format") != FORMAT:
            raise AnswersError("Format de fichier inconnu (attendu : %s)" % FORMAT)
        if document.get("schema_version") != SCHEMA_VERSION:
            raise AnswersError("Version de schema non supportee : %r" % (document.get("schema_version"),))
        unknown = set(document) - {"format", "schema_version", "answers", "exported_at"}
        if unknown:
            raise AnswersError("Champ inconnu dans l'enveloppe : " + sorted(unknown)[0])
        return document.get("answers")
    if document.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise AnswersError("Version de schema non supportee")
    return {k: v for k, v in document.items() if k != "schema_version"}


def parse_answers(data, catalog):
    """Valide integralement des reponses partielles ; retourne un dict normalise."""
    if not isinstance(data, dict):
        raise AnswersError("Reponses : objet JSON attendu")
    unknown = set(data) - FIELDS
    if unknown:
        raise AnswersError("Champ inconnu : " + sorted(unknown)[0])
    name = data.get("name", "")
    if not isinstance(name, str) or not PARTIAL_NAME.fullmatch(name):
        raise AnswersError("Nom de projet invalide (minuscules, chiffres et tirets, 50 caracteres maximum)")
    agents = _ids(data, "agents", len(s.AGENTS))
    if set(agents) - set(s.AGENTS):
        raise AnswersError("Agent inconnu : " + sorted(set(agents) - set(s.AGENTS))[0])
    try:
        answers = {
            "name": name,
            "description": s._text(data, "description", 2000),
            "project_type": s._choice(data, "project_type", s.PROJECT_TYPES, s.PROJECT_TYPES[0]),
            "architecture": s._text(data, "architecture", 4000),
            "technologies": _ids(data, "technologies", s.MAX_TECHNOLOGIES),
            "versions": s._versions(data),
            "agents": [a for a in s.AGENTS if a in agents],
            "security": s._choice(data, "security", s.SECURITY_LEVELS, "strict"),
            "options": s._options(data),
            "external_skills": [dict(zip(s.APPROVAL_FIELDS, item))
                                for item in s._external_skills(data)],
        }
    except s.SpecError as exc:
        raise AnswersError(str(exc)) from exc
    _check_compatibility(answers, catalog)
    return answers


def _check_compatibility(answers, catalog):
    probe = s.ProjectSpec(name="brouillon", description="", project_type=answers["project_type"],
                          technologies=tuple(answers["technologies"]), agents=("codex",),
                          versions=answers["versions"])
    blocking = [x for x in resolve(probe, catalog).diagnostics
                if x.severity.value == "error" and x.code not in TOLERATED]
    if blocking:
        raise AnswersError("; ".join(x.message for x in blocking))


def envelope(answers):
    return {"format": FORMAT, "schema_version": SCHEMA_VERSION, "answers": answers}
