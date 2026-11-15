#!/usr/bin/env python3
"""Lanceur de Forge-my-Project.

Choisit automatiquement un Python 3.11+, reutilise un serveur Forge deja lance,
sinon prend le premier port libre a partir de 8765, puis ouvre le navigateur.

Ce fichier doit rester lisible par un Python ancien (3.6+) : il est souvent lance
avec le `python3` du systeme ou d'Anaconda, trop vieux pour Forge lui-meme.
Pas d'annotation `X | None`, pas d'import de `forge` au niveau du module.
"""
import argparse
import errno
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
import webbrowser

MIN_VERSION = (3, 11)
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_TRIES = 20
NAMES = ("python3.14", "python3.13", "python3.12", "python3.11", "python3", "python")
REEXEC_GUARD = "FORGE_START_REEXEC"
ROOT = os.path.dirname(os.path.abspath(__file__))


def interpreter_version(path):
    """Version (majeure, mineure) d'un interpreteur, ou None s'il ne repond pas."""
    try:
        out = subprocess.run([path, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True)
        major, minor = out.stdout.decode("ascii").split()
        return int(major), int(minor)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def search_dirs():
    """Dossiers du PATH, puis ~/.local/bin (installations utilisateur hors PATH)."""
    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    dirs.append(os.path.join(os.path.expanduser("~"), ".local", "bin"))
    return dirs


def find_interpreter(dirs=None, version=interpreter_version):
    """Premier interpreteur 3.11+ trouve, du plus recent nom au plus generique."""
    seen = set()
    for name in NAMES:
        for directory in dirs if dirs is not None else search_dirs():
            path = shutil.which(name, path=directory)
            if not path:
                continue
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            found = version(path)
            if found is not None and found >= MIN_VERSION:
                return path
    return None


def ensure_python(argv):
    """Relance ce script avec un Python 3.11+ si l'interpreteur courant est trop ancien."""
    if sys.version_info[:2] >= MIN_VERSION:
        return
    current = "{}.{}".format(*sys.version_info[:2])
    path = None if os.environ.get(REEXEC_GUARD) else find_interpreter()
    if path is None:
        sys.exit("Forge requiert Python 3.11 ou plus recent (version utilisee : {}).\n"
                 "Aucun Python 3.11+ trouve dans le PATH ni dans ~/.local/bin.\n"
                 "Installez-en un, ou avec conda : conda create -n forge python=3.12 && conda activate forge"
                 .format(current))
    print("Python {} trop ancien : relance avec {}".format(current, path), flush=True)
    env = dict(os.environ, **{REEXEC_GUARD: "1"})
    # subprocess plutot que os.exec* : meme comportement sous Windows.
    child = subprocess.Popen([path, os.path.abspath(__file__)] + list(argv), env=env)
    while True:
        try:
            sys.exit(child.wait())
        except KeyboardInterrupt:  # Ctrl+C atteint aussi l'enfant, qui s'arrete proprement
            continue


def port_in_use(port):
    """Vrai si un service ecoute deja (bind seul ne suffit pas sous Windows, SO_REUSEADDR)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


def forge_running(port):
    """Vrai si le service sur ce port est deja l'interface Forge."""
    try:
        with urllib.request.urlopen("http://{}:{}/".format(HOST, port), timeout=1) as response:
            return b"<title>Forge-my-Project</title>" in response.read(4096)
    except (OSError, ValueError):
        return False


def bind_server(first_port, tries, make_server):
    """Serveur lie au premier port libre de [first_port, first_port + tries)."""
    for port in range(first_port, min(first_port + tries, 65536)):
        if port_in_use(port):
            continue
        try:
            return make_server((HOST, port))
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
    sys.exit("Aucun port libre entre {} et {} : arretez un service ou utilisez --port."
             .format(first_port, first_port + tries - 1))


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Lance l'interface locale de Forge-my-Project.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="premier port essaye (defaut {}), les suivants si occupe".format(DEFAULT_PORT))
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--new", action="store_true",
                        help="demarrer un nouveau serveur meme si Forge tourne deja sur le port")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port doit etre entre 1 et 65535")
    return args


def open_browser(url, enabled):
    if enabled and not webbrowser.open(url):
        print("Navigateur non ouvert automatiquement : ouvrez l'adresse ci-dessus.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ensure_python(argv)
    args = parse_args(argv)
    if not args.new and forge_running(args.port):
        url = "http://{}:{}".format(HOST, args.port)
        print("Forge tourne deja : {}".format(url))
        open_browser(url, not args.no_browser)
        return 0
    sys.path.insert(0, ROOT)
    from server import Handler, ThreadingHTTPServer  # import tardif : necessite Python 3.11+
    httpd = bind_server(args.port, PORT_TRIES, lambda address: ThreadingHTTPServer(address, Handler))
    url = "http://{}:{}".format(*httpd.server_address[:2])
    if httpd.server_address[1] != args.port:
        print("Port {} occupe : utilisation du port {}".format(args.port, httpd.server_address[1]))
    print("Forge-my-Project : {}  (Ctrl+C pour arreter)".format(url))
    open_browser(url, not args.no_browser)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArret du serveur.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
