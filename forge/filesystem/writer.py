"""Ecriture locale confirmee : sauvegarde, ecriture atomique, controle de concurrence, rollback.

Sequence : (1) relecture de chaque cible et comparaison avec l'etat montre a
l'utilisateur ; (2) copie des fichiers a remplacer dans .forge-backup/<horodatage>/
avec un MANIFEST.json ; (3) pour chaque fichier, fichier temporaire dans le meme
dossier, fsync puis os.replace, apres une derniere verification de l'etat ;
(4) en cas d'echec, restauration des fichiers remplaces et suppression des
fichiers et dossiers crees. Aucun contenu ecrit n'est jamais execute.
"""
import json
import os
import secrets
import time

from forge.filesystem.compare import ABSENT, read_existing
from forge.filesystem.destination import DIR_FLAGS, O_CLOEXEC, O_NOFOLLOW, walk
from forge.generator.archive import EXECUTABLE_PREFIXES

BACKUP_DIR = ".forge-backup"


class StaleError(RuntimeError):
    """La destination a change depuis la comparaison montree a l'utilisateur."""


class WriteFailure(RuntimeError):
    """Echec pendant l'ecriture ; report decrit la restauration effectuee."""

    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def mode_for(path):
    return 0o755 if path.startswith(EXECUTABLE_PREFIXES) else 0o644


def _commit(dir_fd, name, data, mode):
    """Ecrit data dans name de facon atomique (temporaire, fsync, rename) sous dir_fd."""
    temp = ".%s.forge-%s.tmp" % (name[:60], secrets.token_hex(6))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600, dir_fd=dir_fd)
    try:
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            os.unlink(temp, dir_fd=dir_fd)
        except (OSError, ValueError):
            pass
        raise
    os.fsync(dir_fd)


def _parent(dest_fd, path, created):
    parts = path.split("/")
    return walk(os.dup(dest_fd), parts[:-1], create=True, created=created), parts[-1]


def _write_file(dest_fd, path, data, mode, created_dirs):
    parent, name = _parent(dest_fd, path, created_dirs)
    try:
        _commit(parent, name, data, mode)
    finally:
        os.close(parent)


def _check_state(dest_fd, path, expected):
    current = read_existing(dest_fd, path, keep_data=None)
    if current.token != expected:
        raise StaleError("%s a change depuis la comparaison (attendu %s, trouve %s)" % (path, expected, current.token))
    return current


def _stamp():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)


def apply_changes(destination, writes, states):
    """writes : {chemin: (action, bytes)} avec action create|replace|merge ; states : etats compares."""
    dest_created, created_dirs, done, previous = [], [], [], {}
    report = {"destination": destination.path, "backup": None, "operations": [], "status": "ok"}
    with destination.open(create=True, created=dest_created) as dest_fd:
        try:
            for path in sorted(states):
                _check_state(dest_fd, path, states[path])
            for path in sorted(writes):
                if states[path] != ABSENT:
                    previous[path] = read_existing(dest_fd, path, keep_data=None).data
            if previous:
                report["backup"] = _backup(dest_fd, previous, writes, created_dirs)
            for path in sorted(writes):
                action, data = writes[path]
                _check_state(dest_fd, path, states[path])
                _write_file(dest_fd, path, data, mode_for(path), created_dirs)
                done.append(path)
                entry = {"path": path, "action": "created" if path not in previous else
                         ("merged" if action == "merge" else "replaced")}
                if path in previous:
                    entry["backup"] = "%s/%s" % (report["backup"], path)
                report["operations"].append(entry)
        except (StaleError, OSError, ValueError) as exc:
            _rollback(dest_fd, done, previous, created_dirs, report)
            failure = exc
        else:
            failure = None
    if failure is None:
        return report
    _remove_dirs(destination, dest_created)
    if isinstance(failure, StaleError):
        failure.report = report
        raise failure
    raise WriteFailure("Ecriture interrompue (%s) : modifications annulees" % failure, report) from failure


def _remove_dirs(destination, created):
    """Supprime, du plus profond au moins profond, les dossiers de destination crees et restes vides."""
    for parts in sorted(created, key=len, reverse=True):
        try:
            parent = walk(os.open(str(destination.root), DIR_FLAGS), list(parts[:-1]))
            if parent is not None:
                try:
                    os.rmdir(parts[-1], dir_fd=parent)
                finally:
                    os.close(parent)
        except (OSError, ValueError):
            pass


def _backup(dest_fd, previous, writes, created_dirs):
    """Copie des fichiers remplaces + manifeste, avant toute modification des cibles."""
    name = _stamp()
    root = "%s/%s" % (BACKUP_DIR, name)
    manifest = {"created_by": "Forge-my-Project", "backup": root,
                "replaced": sorted(previous), "created": sorted(p for p in writes if p not in previous),
                "restore": "Copier chaque fichier de ce dossier vers le meme chemin relatif de la destination, "
                           "puis supprimer les fichiers listes dans `created`."}
    for path, data in previous.items():
        _write_file(dest_fd, "%s/%s" % (root, path), data, 0o600, created_dirs)
    _write_file(dest_fd, root + "/MANIFEST.json",
                (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), 0o600, created_dirs)
    return root


def _rollback(dest_fd, done, previous, created_dirs, report):
    """Restaure les fichiers remplaces, supprime ceux crees puis les dossiers crees vides."""
    errors = []
    for path in reversed(done):
        try:
            if path in previous:
                _write_file(dest_fd, path, previous[path], mode_for(path), [])
            else:
                parent, name = _parent(dest_fd, path, [])
                try:
                    os.unlink(name, dir_fd=parent)
                finally:
                    os.close(parent)
        except (OSError, ValueError) as exc:
            errors.append("%s : %s" % (path, exc))
    for parts in sorted(created_dirs, key=len, reverse=True):
        if parts and parts[0] == BACKUP_DIR:
            continue  # la sauvegarde est conservee
        try:
            parent = walk(os.dup(dest_fd), list(parts[:-1]))
            if parent is not None:
                try:
                    os.rmdir(parts[-1], dir_fd=parent)
                finally:
                    os.close(parent)
        except (OSError, ValueError):
            pass
    report["status"] = "restored" if not errors else "restore-failed"
    report["operations"] = [{"path": p, "action": "rolled-back"} for p in reversed(done)]
    report["restore_errors"] = errors
