"""Recette finale T18 : parcours complet sur une installation propre, reseau reel.

    python3 tests/acceptance_t18.py --clone <clone propre> --work <dossier vide hors du clone> --out <rapport.json>

Le serveur est lance depuis le clone avec un HOME, une configuration et une racine
d'ecriture vierges (dossiers temporaires). Firefox headless (geckodriver) suit le
parcours utilisateur ; les refus sont ensuite verifies par l'API. Les verifications
en ligne (PyPI/npm, OSV, endoflife.date, registre MCP, GitHub) sont reelles :
un controle impossible est rapporte NON VERIFIE, jamais PASS. Sortie non nulle si
une etape echoue.
"""
import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
BASE = "http://127.0.0.1:8765"


class Check:
    def __init__(self):
        self.results = []

    def record(self, step, status, detail):
        self.results.append({"step": step, "status": status, "detail": detail})
        print("[%s] %s : %s" % (status, step, detail), flush=True)

    def ok(self, step, condition, detail):
        self.record(step, "PASS" if condition else "FAIL", detail)
        return condition


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Browser:
    def __init__(self, profile_root, shots):
        self.port = free_port()
        self.url = "http://127.0.0.1:%d" % self.port
        self.shots = shots
        self.proc = subprocess.Popen(["geckodriver", "--port", str(self.port), "--profile-root", str(profile_root)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     env=dict(os.environ, TMPDIR=str(profile_root)))
        for _ in range(100):
            try:
                self.call("GET", "/status")
                break
            except OSError:
                time.sleep(0.1)
        caps = {"capabilities": {"alwaysMatch": {"browserName": "firefox", "moz:firefoxOptions": {"args": ["-headless"]}}}}
        self.session = self.call("POST", "/session", caps)["sessionId"]
        self.cmd("POST", "/window/rect", {"width": 1366, "height": 1000})

    def call(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())["value"]

    def cmd(self, method, path, payload=None):
        return self.call(method, "/session/%s%s" % (self.session, path), payload)

    def find(self, css):
        return self.cmd("POST", "/element", {"using": "css selector", "value": css})[ELEMENT]

    def js(self, script, *args):
        return self.cmd("POST", "/execute/sync", {"script": script, "args": list(args)})

    def click(self, css):
        self.cmd("POST", "/element/%s/click" % self.find(css), {})

    def type(self, css, text):
        self.cmd("POST", "/element/%s/clear" % self.find(css), {})
        self.cmd("POST", "/element/%s/value" % self.find(css), {"text": text})

    def text(self, css):
        return self.js("return document.querySelector(arguments[0]).textContent", css)

    def wait(self, script, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(script):
                return True
            time.sleep(0.25)
        return False

    def select(self, css, value):
        self.js("const s=document.querySelector(arguments[0]); s.value=arguments[1]; s.dispatchEvent(new Event('change',{bubbles:true}))", css, value)

    def edit(self, css, suffix):
        self.js("const e=document.querySelector(arguments[0]); e.value += arguments[1]; e.dispatchEvent(new Event('input',{bubbles:true}))", css, suffix)

    def shot(self, name):
        with open(os.path.join(self.shots, name + ".png"), "wb") as handle:
            handle.write(base64.b64decode(self.cmd("GET", "/screenshot")))

    def close(self):
        try:
            self.call("DELETE", "/session/" + self.session)
        finally:
            self.proc.terminate()
            self.proc.wait(10)


def api(path, payload):
    request = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def start_server(clone, env, log):
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=clone, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/api/catalog", timeout=2).read()
            return proc
        except OSError:
            time.sleep(0.1)
    proc.terminate()
    raise SystemExit("Serveur non demarre")


def journey(b, check, dest):
    """Etapes 2 a 11 dans l'interface, avec verifications en ligne reelles."""
    b.cmd("POST", "/url", {"url": BASE + "/"})
    check.ok("1 demarrage installation propre", b.wait("return document.querySelectorAll('#profile-select option').length > 1", 30),
             "formulaire charge, 6 profils predefinis attendus : %s options" % b.js("return document.querySelectorAll('#profile-select option').length"))
    # 3. Profil puis personnalisation ; 2. description libre.
    b.select("#profile-select", "typescript-web-react")
    b.click("#profile-load")
    b.type("#name", "recette-boutique")
    b.type("#description", "Boutique en ligne de produits artisanaux : catalogue, panier, suivi des commandes. "
           "Contenu prepare hors de l'outil puis colle ici.")
    b.click('[data-goto="2"]')
    for agent in ("claude", "codex"):
        if not b.js("return document.querySelector('input[name=\"agent\"][value=\"%s\"]').checked" % agent):
            b.click('input[name="agent"][value="%s"]' % agent)
    b.click('[data-goto="0"]')
    b.js("document.querySelector('#architecture').closest('details').open = true")
    b.click("#architecture-suggest")
    suggested = b.wait("return document.querySelector('#architecture').value.length > 20", 30)
    b.edit("#architecture", "\n- Module paiement isole derriere une interface.")
    check.ok("2-3 description libre, profil personnalise, architecture suggeree puis modifiee", suggested,
             "profil typescript-web-react, agents claude+codex, architecture : %d lignes"
             % b.js("return document.querySelector('#architecture').value.split('\\n').length"))
    # 5. Skills (GitHub reel).
    b.click('[data-goto="4"]')
    b.click("#skills-search")
    found = b.wait("return document.querySelector('#skills-candidates li') !== null || document.querySelector('#status').textContent.includes('refus')", 180)
    candidates = b.js("return [...document.querySelectorAll('#skills-candidates [data-skill]')].map(e => e.dataset.skill)")
    approved = None
    if found and candidates:
        recognized = b.js("return [...document.querySelectorAll('#skills-candidates li')].filter(li => li.textContent.includes('source reconnue')).map(li => li.dataset.skill)")
        approved = (recognized or candidates)[0]
        if not recognized:
            b.js("window.confirm = () => true")
        b.click('[data-skill="%s"] [data-action="approve"]' % approved)
        b.click("#skills-verify")
        b.wait("return document.querySelector('#skills-approved [data-status]') && document.querySelector('#skills-approved [data-status]').dataset.status !== 'approuve'", 120)
        status = b.js("return document.querySelector('#skills-approved [data-status]').dataset.status")
        check.ok("5 recherche et approbation de skills (GitHub reel)", status == "PASS",
                 "%d candidats, approuve : %s, reverification : %s" % (len(candidates), approved, status))
    else:
        check.record("5 recherche et approbation de skills (GitHub reel)", "NON VERIFIE", "aucun candidat ou GitHub indisponible : " + b.text("#status"))
    # 6. MCP.
    for server in ("github", "playwright"):
        b.click("#mcp-%s" % server)
    check.ok("6 MCP optionnels", b.js("return document.querySelector('#mcp-github').checked && document.querySelector('#mcp-playwright').checked"),
             "github (lecture seule) et playwright selectionnes")
    # 4, 7, 8. Verification reelle, generation, edition, validation.
    b.click('[data-goto="5"]')
    b.click("#net-verify")
    b.click("#net-skills")
    b.click("#check")
    generated = b.wait("return !document.querySelector('#preview').hidden || document.querySelector('#report').textContent.includes('bloquante')", 300)
    report = b.text("#report")
    statuses = b.js("return [...document.querySelectorAll('#report li')].map(li => li.textContent.split(' - ')[0]).filter(s => ['PASS','FAIL','NON VERIFIE'].includes(s))")
    check.ok("4 technologies et dependances verifiees en ligne", generated and "bloquante" not in report and statuses and "FAIL" not in statuses,
             "%d controles : %d PASS, %d NON VERIFIE, %d FAIL" % (len(statuses), statuses.count("PASS"), statuses.count("NON VERIFIE"), statuses.count("FAIL")))
    b.shot("t18-verification")
    files = b.js("return [...document.querySelectorAll('#files button')].map(e => e.dataset.path)")
    expected = {"AGENTS.md", ".mcp.json", ".codex/config.toml", "docs/MCP.md", ".github/workflows/ci.yml"}
    if approved:
        expected |= {".claude/skills/%s/SKILL.md" % approved, ".agents/skills/%s/SKILL.md" % approved}
    check.ok("7 generation des documents", expected <= set(files), "%d fichiers, attendus presents : %s" % (len(files), sorted(expected - set(files)) or "tous"))
    b.click('[data-path="AGENTS.md"]')
    b.edit("#content", "\n## Note de recette\nModification relue avant ecriture.\n")
    b.click('[data-path="README.md"]')
    b.edit("#content", "\nSection ajoutee dans l'editeur.\n")
    if b.js("return document.querySelector('#ack-warnings') !== null"):
        b.click("#ack-warnings")
    b.click("#validate-files")
    validated = b.wait("return !document.querySelector('#local-write').disabled", 120)
    check.ok("8 verification des fichiers modifies", validated and "2 modifie" in b.text("#status"), b.text("#status"))
    # 9-10. Dossier existant, comparaison, fusion, confirmation.
    b.type("#destination", str(dest))
    b.click("#compare")
    compared = b.wait("return !document.querySelector('#comparison').hidden", 300)
    summary = b.text("#compare-summary")
    check.ok("9 dossier local existant choisi et compare", compared and "Dossier existant" in summary, summary or b.text("#status"))
    if not compared:
        raise RuntimeError("comparaison impossible : " + b.text("#status"))
    conflicts = b.js("return [...document.querySelectorAll('[data-status=\"conflict\"]')].map(e => e.dataset.entry)")
    for path in conflicts:
        b.click('[data-entry="%s"] button' % path)
        if path == "README.md":
            b.click('input[name="resolution"][value="merge"]')
            b.js("const e=document.querySelector('#merge-content'); e.value = e.value + '\\n' + 'Partie generee reprise lors de la fusion.\\n'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        else:
            b.click('input[name="resolution"][value="replace"]')
    b.click("#write-confirm")
    b.js("window.confirm = () => true")
    b.click("#write")
    written = b.wait("return document.querySelector('#write-report').textContent.includes('Ecriture terminee')", 300)
    b.shot("t18-write-report")
    if not written:
        raise RuntimeError("ecriture non terminee : %s %s" % (b.text("#status"), b.text("#write-report")))
    check.ok("10 comparaison, fusion et ecriture confirmee", written and "Partie generee reprise" in (dest / "README.md").read_text()
             and "Modification relue" in (dest / "AGENTS.md").read_text(),
             "conflits : %s ; %s" % (conflicts, b.js("return document.querySelector('#write-report p:nth-of-type(3)')?.textContent || ''")))
    return approved


def backup_and_restore(check, dest, original):
    backups = sorted((dest / ".forge-backup").iterdir())
    manifest = json.loads((backups[-1] / "MANIFEST.json").read_text())
    saved = all((backups[-1] / p).read_bytes() == original[p] for p in manifest["replaced"])
    check.ok("11a sauvegarde des fichiers remplaces", saved and set(manifest["replaced"]) == {"README.md"} | set(manifest["replaced"]),
             "%s : remplaces %s, crees %d" % (manifest["backup"], manifest["replaced"], len(manifest["created"])))
    # Procedure de restauration documentee dans docs/LOCAL_WRITE.md, executee telle quelle.
    script = ('B=%s\n'
              'python3 -c \'import json,sys; print("\\n".join(json.load(open(sys.argv[1]))["created"]))\' "$B/MANIFEST.json" > ../created.txt\n'
              'cp -a "$B/." .  && rm "./MANIFEST.json"\n'
              'xargs -d "\\n" rm -f < ../created.txt\n') % manifest["backup"]
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], cwd=dest, check=True)
    shutil.rmtree(dest / ".forge-backup")
    for directory in sorted((p for p in dest.rglob("*") if p.is_dir() and ".git" not in p.parts), key=lambda p: len(p.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    now = {str(p.relative_to(dest)): p.read_bytes() for p in dest.rglob("*") if p.is_file() and ".git" not in p.parts}
    check.ok("11b restauration manuelle documentee", now == original, "etat initial retrouve : %d fichiers" % len(now))


def generated_ci(check, clone, written):
    """12. Tests et CI du projet ecrit, sur une copie (les installations ne polluent pas la destination)."""
    dest = written.parent / (written.name + "-ci")
    shutil.copytree(written, dest, symlinks=True, ignore=shutil.ignore_patterns(".forge-backup"))
    sys.path.insert(0, str(clone))
    import tests.smoke_generated as smoke  # noqa: E402  (code du clone propre)
    answers = {"technologies": ["typescript", "node", "react", "vitest"]}
    smoke.commit_all(dest, "chore: initialisation par Forge-my-Project")
    env = smoke.environment(dest, answers)
    workflow = (dest / ".github/workflows/ci.yml").read_text()
    failures = []
    for job, steps in smoke.parse_workflow(workflow).items():
        failed = smoke.run_steps(steps, dest, env, "recette/" + job)
        if failed:
            failures.append("%s/%s" % (job, failed))
    for hook in ("pre-commit", "pre-push"):
        if subprocess.run([str(dest / ".githooks" / hook)], cwd=dest, env=env, check=False).returncode:
            failures.append("hook " + hook)
    check.ok("12 tests et CI du projet genere", not failures, "echecs : %s" % (failures or "aucun"))


def refusals(check, dest_root):
    """Refus et erreurs, verifies par l'API sur le serveur de l'installation propre."""
    base = {"schema_version": 1, "name": "refus-demo", "project_type": "api", "description": "",
            "technologies": ["python", "fastapi", "pytest"], "agents": ["claude"]}
    status, body = api("/api/plan", {"config": dict(base, technologies=["python", "django", "fastapi", "pytest"])})
    check.ok("R1 configuration incompatible", status in (400, 422), "statut %d : %s" % (status, json.loads(body).get("error") or [d["message"] for d in json.loads(body)["diagnostics"] if d["severity"] == "error"][:2]))
    status, body = api("/api/plan", {"config": dict(base, name="../../etc")})
    check.ok("R2 nom ou chemin malveillant", status == 400, "statut %d" % status)
    status, body = api("/api/plan", {"config": base})
    files = json.loads(body)["contents"]
    for value in ("/etc/forge", str(dest_root) + "/../x", "relatif"):
        status, body = api("/api/write/compare", {"config": base, "files": files, "destination": value})
        check.ok("R3 destination dangereuse %s" % value, status == 400, json.loads(body)["error"])
    link = dest_root / "lien"
    link.symlink_to("/tmp")
    status, body = api("/api/write/compare", {"config": base, "files": files, "destination": str(link / "p")})
    check.ok("R4 lien symbolique", status == 400, json.loads(body)["error"])
    secret = dict(files, **{"README.md": files["README.md"] + "AKIA" + "Q" * 16 + "\n"})
    status, body = api("/api/files/validate", {"config": base, "files": secret})
    check.ok("R5 secret dans un fichier modifie", status == 400, json.loads(body)["error"])
    mcp = dict(base, mcp_servers=["github"])
    mcp_files = json.loads(api("/api/plan", {"config": mcp})[1])["contents"]
    tampered = dict(mcp_files, **{".mcp.json": mcp_files[".mcp.json"].replace('"true"', '"false"')})
    status, body = api("/api/files/validate", {"config": mcp, "files": tampered})
    check.ok("R6 configuration MCP modifiee (permissions elargies)", status == 400, json.loads(body)["error"])
    dest = dest_root / "concurrent"
    dest.mkdir()
    (dest / "README.md").write_text("avant\n")
    status, body = api("/api/write/compare", {"config": base, "files": files, "destination": str(dest)})
    token = json.loads(body)["token"]
    (dest / "README.md").write_text("modifie par un autre outil\n")
    status, body = api("/api/write/apply", {"config": base, "files": files, "destination": str(dest), "token": token,
                                            "decisions": {"README.md": {"action": "replace"}}, "confirm": True})
    check.ok("R7 modification concurrente", status == 409 and (dest / "README.md").read_text() == "modifie par un autre outil\n"
             and sorted(p.name for p in dest.iterdir()) == ["README.md"], "statut %d, rien ecrit" % status)
    status, body = api("/api/plan", {"config": dict(base, technologies=["python", "fastapi", "pytest", "leftpadx"])})
    check.ok("R8 package inconnu", status == 422, "statut %d" % status)
    status, body = api("/api/plan", {"config": dict(base, versions={"python": "2.7"})})
    check.ok("R9 version non supportee", status in (400, 422), "statut %d" % status)
    status, body = api("/api/plan", {"config": base, "verify": True})
    data = json.loads(body)
    fastapi = [c for c in data.get("verification") or [] if "fastapi" in c["subject"]]
    check.ok("R10 verification reelle d'un package existant", bool(fastapi) and all(c["status"] in ("PASS", "NON VERIFIE") for c in fastapi),
             "; ".join("%s %s" % (c["status"], c["subject"]) for c in fastapi[:3]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clone", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True, help="dossier de travail hors du clone (Firefox snap : hors /tmp)")
    parser.add_argument("--shots", default=None)
    args = parser.parse_args()
    clone = Path(args.clone).resolve()
    work = Path(tempfile.mkdtemp(prefix="forge-t18-", dir=args.work)).resolve()
    if clone == work or clone in work.parents:
        raise SystemExit("--work doit etre hors du clone (une destination dans Forge-my-Project est refusee)")
    shots = args.shots or str(work)
    home, write_root = work / "home", work / "write"
    for path in (home, write_root, work / "firefox"):
        path.mkdir()
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), FORGE_WRITE_ROOT=str(write_root))
    env.pop("FORGE_PROFILES_FILE", None)
    env["GH_CONFIG_DIR"] = os.environ.get("GH_CONFIG_DIR") or str(Path.home() / ".config" / "gh")  # gh reste authentifie
    check = Check()
    dest = write_root / "boutique"
    dest.mkdir()
    (dest / "README.md").write_text("# Boutique\n\nNotes existantes du proprietaire.\n")
    (dest / "notes.txt").write_text("hors generation\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dest, check=True)
    original = {str(p.relative_to(dest)): p.read_bytes() for p in dest.rglob("*") if p.is_file() and ".git" not in p.parts}
    server_log = open(work / "server.log", "w+b")
    server = start_server(clone, env, server_log)
    browser = None
    try:
        browser = Browser(work / "firefox", shots)
        journey(browser, check, dest)
        generated_ci(check, clone, dest)
        backup_and_restore(check, dest, original)
        refusals(check, write_root)
        check.ok("P1 profils personnels dans le HOME vierge", not (home / ".config/forge-my-project/profiles.json").exists()
                 or (home / ".config/forge-my-project/profiles.json").stat().st_mode & 0o077 == 0, "aucun fichier hors HOME de recette")
    except Exception as exc:  # une exception est un echec de recette, jamais un PASS
        check.record("execution", "FAIL", "%s: %s" % (type(exc).__name__, exc))
    finally:
        if browser:
            browser.close()
        server.terminate()
        server.wait(10)
        server_log.seek(0)
        log = server_log.read().decode("utf-8", "replace")
        shutil.copy(work / "server.log", Path(shots) / "server.log")
        check.ok("L1 journal du serveur sans corps de requete ni secret", "AKIA" not in log and "Partie generee" not in log,
                 "%d lignes de journal" % len(log.splitlines()))
    Path(args.out).write_text(json.dumps({"date": time.strftime("%Y-%m-%d %H:%M"), "results": check.results}, indent=2, ensure_ascii=False))
    shutil.rmtree(work / "home", ignore_errors=True)
    failed = [r for r in check.results if r["status"] == "FAIL"]
    print("%d etapes, %d FAIL, %d NON VERIFIE" % (len(check.results), len(failed),
                                                 sum(r["status"] == "NON VERIFIE" for r in check.results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
