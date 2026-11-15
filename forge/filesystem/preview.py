"""Validation des modifications de l'apercu, sans acces au systeme de fichiers."""

from forge.filesystem.content import check_contents
from forge.generator.paths import safe_relative_path

MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


class PreviewError(ValueError):
    """Modification de fichier invalide ou incoherente avec le plan rendu."""


class FileSetMismatch(PreviewError):
    """Les chemins recus different du rendu regenere (edition hors liste ou rendu different)."""


def validate_preview(files, generated):
    """Valide une copie complete des textes affiches dans l'editeur (chemins, tailles, contenu)."""
    if not isinstance(files, dict):
        raise PreviewError("Les fichiers modifies doivent former un objet chemin/contenu")
    expected = set(generated)
    received = set(files)
    if received != expected:
        missing = sorted(expected - received)
        extra = sorted(received - expected)
        details = []
        if missing:
            details.append("absents: " + ", ".join(missing))
        if extra:
            details.append("inattendus: " + ", ".join(extra))
        raise FileSetMismatch("Liste de fichiers incoherente (" + "; ".join(details) + ")")

    validated = {}
    total = 0
    for path in sorted(files):
        safe_relative_path(path)
        content = files[path]
        if not isinstance(content, str) or "\x00" in content:
            raise PreviewError("Contenu texte invalide pour %s" % path)
        try:
            size = len(content.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise PreviewError("Contenu UTF-8 invalide pour %s" % path) from exc
        if size > MAX_FILE_BYTES:
            raise PreviewError("Fichier trop volumineux: %s" % path)
        total += size
        if total > MAX_TOTAL_BYTES:
            raise PreviewError("Ensemble de fichiers trop volumineux")
        validated[path] = content
    check_contents(generated, validated)
    return validated
