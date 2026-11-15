"""Dossier de destination choisi par l'utilisateur, sous une racine autorisee.

Tout acces passe par des descripteurs de dossier ouverts composant par composant
avec O_NOFOLLOW : un lien symbolique place sur le chemin (destination ou fichier
cible) est refuse au lieu d'etre suivi, meme s'il apparait apres la verification.
"""
import os
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

ROOT_ENV = "FORGE_WRITE_ROOT"
FORGE_DIR = Path(__file__).resolve().parents[2]
MAX_PATH = 4096
MAX_LISTED = 300
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
DIR_FLAGS = os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC


class DestinationError(ValueError):
    """Destination refusee (hors racine, lien symbolique, permissions, plateforme)."""


def supported():
    """Ecriture sure uniquement si la plateforme fournit dir_fd et O_NOFOLLOW (Linux, macOS)."""
    return bool(O_NOFOLLOW and O_DIRECTORY) and os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd


def allowed_root():
    value = os.environ.get(ROOT_ENV) or str(Path.home())
    try:
        root = Path(value).resolve(strict=True)
    except OSError as exc:
        raise DestinationError("Racine d'ecriture introuvable : %s" % value) from exc
    if not root.is_dir():
        raise DestinationError("Racine d'ecriture invalide : %s" % value)
    return root


def _segments(value, root):
    if not isinstance(value, str) or not value or len(value) > MAX_PATH or "\x00" in value:
        raise DestinationError("Chemin de destination invalide")
    if any(ord(ch) < 32 for ch in value) or "\\" in value:
        raise DestinationError("Chemin de destination invalide (caracteres de controle ou antislash)")
    pure = PurePosixPath(value)
    if not pure.is_absolute():
        raise DestinationError("Le chemin de destination doit etre absolu")
    if any(part in (".", "..") for part in value.split("/")) or os.path.normpath(value) != value:
        raise DestinationError("Chemin de destination non normalise (., .., // ou / final interdits)")
    try:
        relative = pure.relative_to(PurePosixPath(root))
    except ValueError as exc:
        raise DestinationError("Destination hors de la racine autorisee %s" % root) from exc
    parts = relative.parts
    if not parts:
        raise DestinationError("Choisir un sous-dossier de la racine autorisee, pas la racine elle-meme")
    if any(len(part.encode("utf-8")) > 255 for part in parts):
        raise DestinationError("Nom de dossier trop long")
    return parts


class Destination:
    """Destination validee : racine reelle et segments relatifs (aucun lien suivi)."""

    def __init__(self, value, root=None):
        if not supported():
            raise DestinationError("Ecriture locale non supportee sur cette plateforme (dir_fd/O_NOFOLLOW requis)")
        self.root = Path(root).resolve(strict=True) if root else allowed_root()
        self.parts = _segments(value, self.root)
        self.path = value
        candidate = Path(value)
        if candidate == FORGE_DIR or FORGE_DIR in candidate.parents:
            raise DestinationError("Destination interdite : dossier de Forge-my-Project")

    @contextmanager
    def open(self, create=False, created=None):
        """Descripteur du dossier de destination, ou None s'il n'existe pas (create=False)."""
        fd = walk(os.open(str(self.root), DIR_FLAGS), self.parts, create, created, self.path)
        try:
            yield fd
        finally:
            if fd is not None:
                os.close(fd)

    def describe(self):
        """Etat de la destination : existence, droit d'ecriture, nombre d'entrees."""
        with self.open() as fd:
            if fd is not None:
                entries = len(os.listdir(fd))
                writable = os.access(self.path, os.W_OK | os.X_OK)
                return {"path": self.path, "exists": True, "writable": writable, "empty": entries == 0}
        ancestor = self._nearest_existing()
        writable = os.access(str(ancestor), os.W_OK | os.X_OK)
        return {"path": self.path, "exists": False, "writable": writable, "empty": True}

    def _nearest_existing(self):
        fd = os.open(str(self.root), DIR_FLAGS)
        current = self.root
        try:
            for part in self.parts:
                try:
                    child = os.open(part, DIR_FLAGS, dir_fd=fd)
                except FileNotFoundError:
                    return current
                except OSError as exc:
                    raise DestinationError("Chemin refuse (lien symbolique ou fichier) : %s" % (current / part)) from exc
                os.close(fd)
                fd, current = child, current / part
            return current
        finally:
            os.close(fd)


def walk(fd, parts, create=False, created=None, label=""):
    """Descend dans parts depuis fd (qui est consomme) ; liens et fichiers refuses."""
    for index, part in enumerate(parts):
        try:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
        except FileNotFoundError:
            if not create:
                os.close(fd)
                return None
            try:
                os.mkdir(part, 0o755, dir_fd=fd)
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                os.close(fd)
                raise DestinationError("Creation impossible de %s : %s" % ("/".join(parts[:index + 1]), exc.strerror)) from exc
            if created is not None:
                created.append(tuple(parts[:index + 1]))
        except OSError as exc:
            os.close(fd)
            raise DestinationError("Chemin refuse (lien symbolique ou fichier) : %s/%s"
                                   % (label, "/".join(parts[:index + 1])) if label else "/".join(parts[:index + 1])) from exc
        os.close(fd)
        fd = child
    return fd


def browse(value=None, root=None):
    """Sous-dossiers d'un dossier sous la racine (liens symboliques et dossiers caches exclus)."""
    base = Path(root).resolve(strict=True) if root else allowed_root()
    if value in (None, "", str(base)):
        parts, path = (), str(base)
    else:
        parts, path = _segments(value, base), value
    fd = walk(os.open(str(base), DIR_FLAGS), parts, label=str(base))
    if fd is None:
        raise DestinationError("Dossier introuvable : %s" % path)
    try:
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if entry.name.startswith(".") or not entry.is_dir(follow_symlinks=False):
                    continue
                names.append(entry.name)
    finally:
        os.close(fd)
    names.sort(key=str.lower)
    parent = str(Path(path).parent) if parts else None
    return {"root": str(base), "path": path, "parent": parent,
            "directories": names[:MAX_LISTED], "truncated": len(names) > MAX_LISTED,
            "writable": os.access(path, os.W_OK | os.X_OK)}


def is_regular(fd_stat):
    return stat.S_ISREG(fd_stat.st_mode)
