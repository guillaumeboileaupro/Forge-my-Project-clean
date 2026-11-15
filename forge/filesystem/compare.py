"""Comparaison des fichiers prepares avec le contenu present dans la destination."""
import difflib
import hashlib
import os
import stat

from forge.filesystem.destination import O_CLOEXEC, O_NOFOLLOW, walk
from forge.generator.paths import safe_relative_path

MAX_MERGEABLE = 256 * 1024
MAX_DIFF_LINES = 400
ABSENT = "absent"


class Existing:
    """Etat d'un chemin dans la destination : absent, fichier (empreinte) ou bloque."""

    def __init__(self, kind, digest=None, data=None, reason=""):
        self.kind, self.digest, self.data, self.reason = kind, digest, data, reason

    @property
    def token(self):
        if self.kind == "file":
            return self.digest
        return ABSENT if self.kind == ABSENT else "blocked"


def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read_existing(dest_fd, path, keep_data=MAX_MERGEABLE):
    """Lit path sous dest_fd sans suivre de lien ; keep_data=None conserve tout le contenu."""
    parts = safe_relative_path(path).split("/")
    if dest_fd is None:
        return Existing(ABSENT)
    try:
        parent = walk(os.dup(dest_fd), parts[:-1])
    except ValueError:
        return Existing("blocked", reason="lien symbolique ou fichier sur le chemin")
    if parent is None:
        return Existing(ABSENT)
    try:
        try:
            fd = os.open(parts[-1], os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        except FileNotFoundError:
            return Existing(ABSENT)
        except OSError:
            return Existing("blocked", reason="lien symbolique ou entree illisible")
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                return Existing("blocked", reason="entree existante qui n'est pas un fichier ordinaire")
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    kept = data if keep_data is None or len(data) <= keep_data else None
    return Existing("file", sha256(data), kept)


def _text(data):
    try:
        return data.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return None


def unified_diff(existing, generated, path):
    lines = list(difflib.unified_diff(existing.splitlines(keepends=True), generated.splitlines(keepends=True),
                                      "existant/" + path, "prepare/" + path, n=3))
    truncated = len(lines) > MAX_DIFF_LINES
    text = "".join(line if line.endswith("\n") else line + "\n" for line in lines[:MAX_DIFF_LINES])
    return text + ("... diff tronque (%d lignes)\n" % len(lines) if truncated else "")


def compare(dest_fd, files):
    """Entrees triees {path, status, ...} et etats {path: empreinte|absent|blocked}."""
    entries, states = [], {}
    for path in sorted(files):
        content = files[path]
        existing = read_existing(dest_fd, path)
        states[path] = existing.token
        entry = {"path": path, "status": "new", "diff": "", "existing": None, "mergeable": False, "reason": ""}
        if existing.kind == "blocked":
            entry.update(status="blocked", reason=existing.reason)
        elif existing.kind == "file":
            if existing.digest == sha256(content.encode("utf-8")):
                entry["status"] = "identical"
            else:
                text = _text(existing.data)
                entry["status"] = "conflict"
                if text is None or "\x00" in (text or ""):
                    entry["reason"] = "contenu existant binaire ou trop volumineux : conserver ou remplacer"
                else:
                    entry.update(diff=unified_diff(text, content, path), existing=text, mergeable=True)
        entries.append(entry)
    return entries, states
