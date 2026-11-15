"""Recette navigateur du formulaire hybride (Firefox headless via WebDriver).

Active uniquement avec FORGE_E2E=1 et geckodriver + firefox disponibles :
    FORGE_E2E=1 python3 -m unittest tests.test_e2e_firefox -v
Protocole WebDriver W3C pilote avec urllib : aucune dependance tierce.
"""
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
import zipfile
from unittest import mock

from server import Handler, ThreadingHTTPServer
from tests.test_engine_external_skills import CONFIG as SKILL_CONFIG
from tests.test_engine_external_skills import FakeClient, FakeGh, modified_repos

ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
ENABLED = os.environ.get("FORGE_E2E") == "1" and shutil.which("geckodriver") and shutil.which("firefox")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(ENABLED, "FORGE_E2E=1, geckodriver et firefox requis")
class FirefoxFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles_dir = tempfile.mkdtemp(prefix="forge-e2e-profiles-")
        cls.write_root = os.path.realpath(tempfile.mkdtemp(prefix="forge-e2e-write-"))
        cls.env = mock.patch.dict(os.environ, {"FORGE_PROFILES_FILE": os.path.join(cls.profiles_dir, "profiles.json"),
                                               "FORGE_WRITE_ROOT": cls.write_root})
        cls.env.start()
        # GitHub remplace par un faux client : aucun acces reseau pendant la recette.
        cls.skill_client = FakeGh()
        cls.skill_patches = [mock.patch("forge.skills.service.default_client", lambda: cls.skill_client),
                             mock.patch("forge.skills.service.b.load_copy_policy", lambda: SKILL_CONFIG)]
        for patch in cls.skill_patches:
            patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        # Firefox snap n'accede pas au /tmp prive : profil dans un dossier ignore du depot.
        root = os.environ.get("FORGE_E2E_TMP") or os.path.join(os.getcwd(), ".tmp-e2e")
        os.makedirs(root, exist_ok=True)
        cls.tmp = tempfile.mkdtemp(prefix="forge-e2e-", dir=root)
        port = free_port()
        cls.driver_url = "http://127.0.0.1:%d" % port
        cls.driver = subprocess.Popen(["geckodriver", "--port", str(port), "--profile-root", cls.tmp], stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, env=dict(os.environ, TMPDIR=cls.tmp))
        for _ in range(100):
            try:
                cls.call("GET", "/status")
                break
            except OSError:
                time.sleep(0.1)
        caps = {"capabilities": {"alwaysMatch": {"browserName": "firefox",
                                                 "moz:firefoxOptions": {"args": ["-headless"]}}}}
        cls.session = cls.call("POST", "/session", caps)["sessionId"]

    @classmethod
    def tearDownClass(cls):
        try:
            cls.call("DELETE", "/session/" + cls.session)
        finally:
            cls.driver.terminate()
            cls.driver.wait(10)
            cls.server.shutdown()
            cls.server.server_close()
            cls.env.stop()
            for patch in cls.skill_patches:
                patch.stop()
            shutil.rmtree(cls.tmp, ignore_errors=True)
            shutil.rmtree(cls.profiles_dir, ignore_errors=True)
            shutil.rmtree(cls.write_root, ignore_errors=True)

    def setUp(self):
        """Chaque parcours part d'un navigateur sans brouillon."""
        self.open_with_storage(None)

    def open_with_storage(self, draft):
        # Le stockage est prepare depuis une page du meme domaine sans l'application,
        # sinon la sauvegarde a la fermeture (pagehide) reecrirait le brouillon.
        self.cmd("POST", "/url", {"url": self.base + "/css/app.css"})
        self.js("localStorage.clear(); if (arguments[0]) localStorage.setItem('forge-my-project.draft.v1', arguments[0]);", draft)
        self.cmd("POST", "/url", {"url": self.base + "/"})
        self.wait_ready()

    def wait_ready(self):
        self.wait("return document.querySelectorAll('#profile-select option').length > 1")

    @classmethod
    def call(cls, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(cls.driver_url + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())["value"]

    def cmd(self, method, path, payload=None):
        return self.call(method, "/session/%s%s" % (self.session, path), payload)

    def find(self, css):
        return self.cmd("POST", "/element", {"using": "css selector", "value": css})[ELEMENT]

    def js(self, script, *args):
        return self.cmd("POST", "/execute/sync", {"script": script, "args": list(args)})

    def click(self, css):
        self.cmd("POST", "/element/%s/click" % self.find(css), {})

    def wait(self, script, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(script):
                return
            time.sleep(0.1)
        self.fail("Condition non atteinte : " + script)

    def visible(self, css):
        return self.cmd("GET", "/element/%s/displayed" % self.find(css))

    def screenshot(self, name):
        """Capture optionnelle (FORGE_E2E_SCREENSHOTS=dossier) pour controle visuel."""
        target = os.environ.get("FORGE_E2E_SCREENSHOTS")
        if target:
            with open(os.path.join(target, name + ".png"), "wb") as handle:
                handle.write(base64.b64decode(self.cmd("GET", "/screenshot")))

    def type_text(self, css, text):
        self.cmd("POST", "/element/%s/clear" % self.find(css), {})
        self.cmd("POST", "/element/%s/value" % self.find(css), {"text": text})

    def validate_files(self):
        """Confirme les avertissements eventuels (exigence : avertissement et confirmation) puis valide."""
        if self.js("return document.querySelector('#ack-warnings') !== null && !document.querySelector('#ack-warnings').checked"):
            self.click("#ack-warnings")
        self.click("#validate-files")

    def checked(self, css):
        return self.js("return document.querySelector(arguments[0]).checked", css)

    def test_autosave_restores_conditional_answers(self):
        self.type_text("#name", "draft-demo")
        self.click('[data-goto="1"]')
        for css in ("#tech-node", "#tech-typescript", "#tech-vitest"):
            self.click(css)
        self.js("const s=document.querySelector('[data-version=\"node\"]'); s.value='22'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.wait("return (localStorage.getItem('forge-my-project.draft.v1') || '').includes('vitest')")
        self.assertIn("sauvegardees", self.js("return document.querySelector('#autosave-status').textContent"))
        self.cmd("POST", "/refresh", {})
        self.wait("return document.querySelector('#autosave-status').textContent.includes('restaurees')")
        self.assertEqual(self.js("return document.querySelector('#name').value"), "draft-demo")
        self.assertTrue(self.checked("#tech-vitest"))
        self.assertTrue(self.js("return !document.querySelector('[data-tech=\"vitest\"]').hidden"))
        self.assertEqual(self.js("return document.querySelector('[data-version=\"node\"]').value"), "22")
        self.click('[data-goto="1"]')
        self.click("#tech-eslint")
        self.cmd("POST", "/refresh", {})  # rechargement immediat : sauvegarde a la fermeture
        self.wait("return document.querySelector('#autosave-status').textContent.includes('restaurees')")
        self.assertTrue(self.checked("#tech-eslint"))
        self.click("#reset")
        self.assertFalse(self.checked("#tech-typescript"))
        self.assertIsNone(self.js("return localStorage.getItem('forge-my-project.draft.v1')"))

    def test_incompatible_draft_is_not_restored(self):
        draft = {"format": "forge-my-project/answers", "schema_version": 1, "answers": {"technologies": ["cobol"]}}
        self.open_with_storage(json.dumps(draft))
        self.wait("return document.querySelector('#alert').textContent.includes('Brouillon precedent ignore')")
        self.assertIsNone(self.js("return localStorage.getItem('forge-my-project.draft.v1')"))

    def test_profiles_lifecycle(self):
        self.type_text("#name", "profil-demo")
        self.js("const s=document.querySelector('#profile-select'); s.value='typescript-web-react'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.click("#profile-load")
        self.assertTrue(self.checked("#tech-react"))
        self.assertFalse(self.js("return document.querySelector('[data-tech=\"node\"] .version').hidden"))
        self.assertEqual(self.js("return document.querySelector('#name').value"), "profil-demo")
        self.click('[data-goto="1"]')
        self.click("#tech-prettier")  # reponses modifiables apres chargement
        self.click('[data-goto="0"]')
        self.js("document.querySelector('#profile-manage').open = true")
        self.js("const s=document.querySelector('#profile-select'); s.value=''; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.type_text("#profile-label", "E2E perso")
        self.screenshot("profils")
        self.click("#profile-create")
        self.wait("return document.querySelector('#profile-select').value === 'e2e-perso'")
        self.type_text("#profile-label", "E2E perso v2")
        self.click("#profile-update")
        self.wait("return [...document.querySelectorAll('#profile-select option')].some(o => o.textContent === 'E2E perso v2')")
        self.click("#profile-delete")
        self.cmd("POST", "/alert/accept", {})
        self.wait("return ![...document.querySelectorAll('#profile-select option')].some(o => o.value === 'e2e-perso')")

    def test_export_then_import(self):
        self.type_text("#name", "export-demo")
        self.click('[data-goto="1"]')
        self.click("#tech-python")
        self.click("#tech-pytest")
        self.js("window.__blobs=[]; URL.createObjectURL = blob => { window.__blobs.push(blob); return 'blob:test'; };")
        self.click("#export")
        self.wait("return window.__blobs.length === 1")
        exported = json.loads(self.cmd("POST", "/execute/async", {
            "script": "arguments[0].length; window.__blobs[0].text().then(arguments[arguments.length - 1])", "args": [[]]}))
        self.assertEqual(exported["format"], "forge-my-project/answers")
        self.assertEqual(exported["answers"]["technologies"], ["python", "pytest"])
        self.click("#reset")
        path = os.path.join(self.tmp, "import.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(exported, handle)
        self.cmd("POST", "/element/%s/value" % self.find("#import"), {"text": path})
        self.wait("return document.querySelector('#tech-pytest').checked")
        self.assertEqual(self.js("return document.querySelector('#name').value"), "export-demo")
        for content, message in (("{pas du json", "pas un JSON valide"),
                                 (json.dumps({"technologies": ["python", "flask", "django"]}), "incompatible")):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            self.cmd("POST", "/element/%s/value" % self.find("#import"), {"text": path})
            self.wait("return document.querySelector('#alert').textContent.includes(arguments[0])".replace(
                "arguments[0]", json.dumps(message)))
        self.assertTrue(self.checked("#tech-pytest"))  # un import refuse ne modifie rien

    def test_full_journey(self):
        # Section 1 : badge d'erreur tant que le nom est invalide.
        self.assertFalse(self.js("return document.querySelector('[data-goto=\"0\"] .badge').hidden"))
        self.cmd("POST", "/element/%s/value" % self.find("#name"), {"text": "e2e-demo"})
        self.js("const s=document.querySelector('#project_type'); s.value='api'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.wait("return document.querySelector('[data-goto=\"0\"] .badge').hidden")
        self.click("#next")
        # Section 2 : questions conditionnelles.
        self.assertFalse(self.visible('[data-tech="pytest"]'))
        self.click("#tech-python")
        self.wait("return !document.querySelector('[data-tech=\"pytest\"]').hidden")
        self.assertTrue(self.visible('[data-tech="python"] .version'))
        self.click("#tech-fastapi")
        self.click("#tech-pytest")
        self.screenshot("technologies")
        self.assertTrue(self.js("return document.querySelector('#tech-flask').disabled"))
        # Retrait en cascade puis reselection.
        self.click("#tech-python")
        self.wait("return !document.querySelector('#tech-fastapi').checked && !document.querySelector('#tech-pytest').checked")
        for css in ("#tech-python", "#tech-fastapi", "#tech-pytest"):
            self.click(css)
        # Section 3 : agents, puis verification.
        self.click('[data-goto="2"]')
        self.click('input[name="agent"][value="claude"]')
        self.click('[data-goto="5"]')
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden")
        files = self.js("return [...document.querySelectorAll('#files button')].map(b => b.dataset.path)")
        self.assertIn("AGENTS.md", files)
        self.assertIn("CLAUDE.md", files)
        self.assertIn("e2e-demo", self.js("return document.querySelector('#content').value"))
        self.assertTrue(self.js("return document.querySelector('#download').disabled"))
        # Edition, indication du changement, navigation et validation serveur.
        self.js("const e=document.querySelector('#content'); e.value += '\\nAjout relu.\\n'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        self.assertEqual(self.js("return document.querySelector('#edit-status').textContent"), "Modifie")
        self.assertFalse(self.js("return document.querySelector('[data-modified=\"AGENTS.md\"]').hidden"))
        self.click("#next-file")
        self.assertNotEqual(self.js("return document.querySelector('#file-title').textContent"), "AGENTS.md")
        self.click('[data-path="AGENTS.md"]')
        self.assertIn("Ajout relu.", self.js("return document.querySelector('#content').value"))
        self.validate_files()
        self.wait("return !document.querySelector('#download').disabled")
        self.assertIn("1 modifie", self.js("return document.querySelector('#status').textContent"))
        self.screenshot("verification")
        # Une modification invalide l'apercu valide.
        self.click('[data-goto="0"]')
        self.cmd("POST", "/element/%s/value" % self.find("#description"), {"text": "x"})
        self.assertTrue(self.js("return document.querySelector('#download').disabled"))

    def text(self, css):
        return self.js("return document.querySelector(arguments[0]).textContent", css)

    def test_external_skills_approval(self):
        type(self).skill_client = FakeGh()
        draft = {"format": "forge-my-project/answers", "schema_version": 1, "answers": {
            "name": "shop-web", "project_type": "web", "agents": ["claude"],
            "technologies": ["node", "typescript", "react", "vitest"]}}
        self.open_with_storage(json.dumps(draft))
        self.click('[data-goto="4"]')
        self.click("#skills-search")
        self.wait("return document.querySelectorAll('#skills-candidates [data-skill]').length === 2")
        card = self.text('[data-skill="webapp-testing"]')
        for expected in ("Test React web apps", "anthropics/skills/skills", "a" * 40, "source reconnue", "run.py"):
            self.assertIn(expected, card)
        self.assertIn("source non reconnue", self.text('[data-skill="react-helper"]'))
        self.click('[data-skill="webapp-testing"] [data-action="approve"]')
        self.click('[data-skill="react-helper"] [data-action="refuse"]')
        self.assertIn("Refuse", self.text('[data-skill="react-helper"] .decision'))
        self.assertEqual(self.js("return document.querySelectorAll('#skills-approved [data-approved]').length"), 1)
        self.screenshot("skills")
        # Conservation : brouillon recharge, puis verification en ligne (faux GitHub).
        self.wait("return (localStorage.getItem('forge-my-project.draft.v1') || '').includes('sha256:')")
        self.cmd("POST", "/refresh", {})
        self.wait("return document.querySelector('#autosave-status').textContent.includes('restaurees')")
        self.assertIn("webapp-testing", self.text("#skills-approved"))
        self.click('[data-goto="4"]')
        self.click("#skills-verify")
        self.wait("return document.querySelector('#skills-approved [data-status]').dataset.status === 'PASS'")
        # Le skill change cote GitHub : verification en echec et generation bloquee.
        type(self).skill_client = FakeClient(repos=modified_repos("skills/webapp-testing/SKILL.md", "change"))
        self.click("#skills-verify")
        self.wait("return document.querySelector('#skills-approved [data-status]').dataset.status === 'FAIL'")
        self.click('[data-goto="5"]')
        self.click("#net-skills")
        self.click("#check")
        self.wait("return document.querySelector('#report').textContent.includes('modifie depuis son approbation')")
        self.assertTrue(self.js("return document.querySelector('#download').disabled"))
        # Retrait de l'approbation : la generation redevient possible.
        self.click('[data-goto="4"]')
        self.click('#skills-approved button')
        self.assertTrue(self.visible("#skills-empty"))
        self.click('[data-goto="5"]')
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden")
        self.validate_files()
        self.wait("return !document.querySelector('#download').disabled")

    def test_mcp_selection(self):
        self.type_text("#name", "mcp-demo")
        self.js("const s=document.querySelector('#project_type'); s.value='web'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.click('[data-goto="1"]')
        for css in ("#tech-node", "#tech-typescript", "#tech-vitest"):
            self.click(css)
        self.click('[data-goto="2"]')
        self.click('input[name="agent"][value="claude"]')
        self.click('[data-goto="4"]')
        self.assertTrue(self.visible('[data-mcp="playwright"]'))
        self.assertFalse(self.checked("#mcp-github") or self.checked("#mcp-playwright"))  # rien par defaut
        self.click("#mcp-playwright")
        self.click("#mcp-github")
        self.assertIn("GITHUB_PERSONAL_ACCESS_TOKEN", self.text('[data-mcp="github"]'))
        self.screenshot("mcp")
        # Un projet API ne propose plus Playwright : selection retiree.
        self.click('[data-goto="0"]')
        self.js("const s=document.querySelector('#project_type'); s.value='api'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.click('[data-goto="4"]')
        self.assertFalse(self.visible('[data-mcp="playwright"]'))
        self.assertFalse(self.checked("#mcp-playwright"))
        self.click('[data-goto="0"]')
        self.js("const s=document.querySelector('#project_type'); s.value='web'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.click('[data-goto="5"]')
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden")
        files = self.js("return [...document.querySelectorAll('#files button')].map(b => b.dataset.path)")
        self.assertIn(".mcp.json", files)
        self.assertIn("docs/MCP.md", files)
        self.assertNotIn(".codex/config.toml", files)
        # Edition de la documentation MCP, validation puis archive : l'edition est dans le ZIP.
        self.click('[data-path="docs/MCP.md"]')
        self.js("const e=document.querySelector('#content'); e.value += '\\nRelu avant activation.\\n'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        self.validate_files()
        self.wait("return !document.querySelector('#download').disabled")
        archive = self.capture_archive()
        self.assertTrue(archive.read("mcp-demo/docs/MCP.md").decode().endswith("Relu avant activation.\n"))
        self.assertEqual(json.loads(archive.read("mcp-demo/.mcp.json"))["mcpServers"].keys(), {"github"})
        # Changer la selection MCP invalide l'apercu valide, puis la regeneration retire les fichiers.
        self.click('[data-goto="4"]')
        self.click("#mcp-github")
        self.assertTrue(self.js("return document.querySelector('#download').disabled"))
        self.click('[data-goto="5"]')
        self.validate_files()
        self.wait("return document.querySelector('#status').textContent.includes('relancer la verification')")
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden && !document.querySelector('[data-path=\"docs/MCP.md\"]')")
        files = self.js("return [...document.querySelectorAll('#files button')].map(b => b.dataset.path)")
        self.assertFalse({".mcp.json", "docs/MCP.md"} & set(files))

    def capture_archive(self):
        """Clique sur Telecharger et relit le ZIP recu, sans laisser Firefox l'ecrire sur disque."""
        self.js("""window.__zip = null;
            HTMLAnchorElement.prototype.click = function () {};
            const original = window.fetch;
            window.fetch = async (path, init) => {
              const response = await original(path, init);
              if (path === '/api/archive') {
                const bytes = new Uint8Array(await response.clone().arrayBuffer());
                let text = ''; for (const b of bytes) text += String.fromCharCode(b);
                window.__zip = btoa(text);
              }
              return response;
            };""")
        self.click("#download")
        self.wait("return window.__zip !== null && document.querySelector('#status').textContent === 'Archive generee.'")
        return zipfile.ZipFile(io.BytesIO(base64.b64decode(self.js("return window.__zip"))))

    def test_editor_and_skill_approval_interact(self):
        """Une approbation retiree apres validation de l'apercu oblige a regenerer."""
        type(self).skill_client = FakeGh()
        self.type_text("#name", "skills-edit")
        self.js("const s=document.querySelector('#project_type'); s.value='web'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.click('[data-goto="1"]')
        for css in ("#tech-node", "#tech-typescript", "#tech-react", "#tech-vitest"):
            self.click(css)
        self.click('[data-goto="2"]')
        self.click('input[name="agent"][value="claude"]')
        self.click('[data-goto="4"]')
        self.click("#skills-search")
        self.wait("return document.querySelector('[data-skill=\"webapp-testing\"]') !== null")
        self.click('[data-skill="webapp-testing"] [data-action="approve"]')
        self.click('[data-goto="5"]')
        self.click("#net-skills")
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden")
        path = ".claude/skills/webapp-testing/SKILL.md"
        self.click('[data-path="%s"]' % path)
        self.js("const e=document.querySelector('#content'); e.value += '\\nNote locale.\\n'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        self.assertFalse(self.js("return document.querySelector('[data-modified=\"%s\"]').hidden" % path))
        self.validate_files()
        self.wait("return !document.querySelector('#download').disabled")
        archive = self.capture_archive()
        self.assertTrue(archive.read("skills-edit/" + path).decode().endswith("Note locale.\n"))
        self.assertFalse([n for n in archive.namelist() if "/skills/" in n and n.endswith(".py")])
        self.click('[data-goto="4"]')
        self.click('#skills-approved button')
        self.assertTrue(self.js("return document.querySelector('#download').disabled"))


    def test_local_write_journey(self):
        """Destination existante : conflits, fusion manuelle, confirmation, sauvegarde, puis validation perimee."""
        from pathlib import Path
        dest = Path(self.write_root) / "clients" / "write-demo"
        (dest / "docs").mkdir(parents=True)
        (dest / "README.md").write_text("README existant\n")
        (dest / "notes.txt").write_text("hors generation\n")
        self.type_text("#name", "write-demo")
        self.click('[data-goto="1"]')
        for css in ("#tech-python", "#tech-pytest"):
            self.click(css)
        self.click('[data-goto="2"]')
        self.click('input[name="agent"][value="claude"]')
        self.click('[data-goto="5"]')
        self.assertTrue(self.js("return document.querySelector('#local-write').disabled"))
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden")
        self.click('[data-path="AGENTS.md"]')
        self.js("const e=document.querySelector('#content'); e.value += '\\nEdition locale.\\n'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        self.validate_files()
        self.wait("return !document.querySelector('#local-write').disabled")
        self.assertEqual(self.text("#dest-root"), self.write_root)
        # Navigation dans la racine autorisee jusqu'au dossier existant.
        self.click("#browse")
        self.wait("return document.querySelector('[data-dir=\"clients\"]') !== null")
        self.click('[data-dir="clients"]')
        self.wait("return document.querySelector('[data-dir=\"write-demo\"]') !== null")
        self.click('[data-dir="write-demo"]')
        self.wait("return document.querySelector('#destination').value.endsWith('/write-demo')")
        self.click("#compare")
        self.wait("return !document.querySelector('#comparison').hidden")
        self.assertIn("1 conflit(s)", self.text("#compare-summary"))
        self.assertEqual(self.js("return document.querySelector('[data-entry=\"README.md\"]').dataset.status"), "conflict")
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["README.md", "docs", "notes.txt"])  # rien d'ecrit
        self.click("#write-confirm")
        self.assertTrue(self.js("return document.querySelector('#write').disabled"))  # conflit sans decision
        self.click('[data-entry="README.md"] button')
        self.assertIn("-README existant", self.text("#diff"))
        self.click('input[name="resolution"][value="merge"]')
        self.js("const e=document.querySelector('#merge-content'); e.value = 'README existant\\nFusion relue.\\n'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        self.wait("return !document.querySelector('#write').disabled")
        self.js("window.confirm = () => true")
        self.screenshot("write-compare")
        self.click("#write")
        self.wait("return document.querySelector('#write-report').textContent.includes('Ecriture terminee')")
        self.screenshot("write-report")
        self.assertEqual((dest / "README.md").read_text(), "README existant\nFusion relue.\n")
        self.assertTrue((dest / "AGENTS.md").read_text().endswith("Edition locale.\n"))
        self.assertEqual((dest / "notes.txt").read_text(), "hors generation\n")
        backups = list((dest / ".forge-backup").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "README.md").read_text(), "README existant\n")
        self.assertIn("fusionne : README.md", self.text("#write-report"))
        # Nouvelle comparaison puis modification concurrente : ecriture refusee (409), rien d'ecrase.
        self.click("#compare")
        self.wait("return !document.querySelector('#comparison').hidden")
        self.assertIn("0 nouveau(x)", self.text("#compare-summary"))
        self.assertIn("1 conflit(s)", self.text("#compare-summary"))  # README fusionne != fichier prepare
        self.click('[data-entry="README.md"] button')
        self.click('input[name="resolution"][value="keep"]')
        (dest / "CLAUDE.md").write_text("modifie par un autre outil\n")
        self.click("#write-confirm")
        self.click("#write")
        self.wait("return document.querySelector('#status').textContent.includes('Validation perimee')")
        self.assertEqual((dest / "CLAUDE.md").read_text(), "modifie par un autre outil\n")
        # Une modification de la configuration desactive l'ecriture.
        self.click('[data-goto="0"]')
        self.cmd("POST", "/element/%s/value" % self.find("#description"), {"text": "x"})
        self.assertTrue(self.js("return document.querySelector('#local-write').disabled"))

    def test_questionnaire_search_suggestion_and_warning_confirmation(self):
        """T03/T04 : recherche, retour arriere, cascade des dependances, suggestion d'architecture, avertissements."""
        self.type_text("#name", "quest-demo")
        self.js("const s=document.querySelector('#project_type'); s.value='api'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        self.click("#next")
        # Questions progressives : FastAPI n'apparait qu'avec Python.
        self.assertFalse(self.visible("#tech-fastapi"))
        self.click("#tech-python")
        self.assertTrue(self.visible("#tech-fastapi"))
        self.click("#tech-fastapi")
        self.click("#tech-pytest")
        # Recherche : filtre l'affichage sans perdre les choix.
        self.type_text("#tech-search", "fast")
        self.assertTrue(self.visible("#tech-fastapi"))
        self.assertFalse(self.visible("#tech-pytest"))
        self.assertTrue(self.checked("#tech-pytest"))
        self.assertIn("affichee", self.text("#tech-search-help"))
        self.type_text("#tech-search", "")
        self.js("const e=document.querySelector('#tech-search'); e.dispatchEvent(new Event('input',{bubbles:true}))")
        self.assertTrue(self.visible("#tech-pytest"))
        # Cascade : retirer Python retire FastAPI et pytest (prerequis disparus).
        self.click("#tech-python")
        self.wait("return !document.querySelector('#tech-fastapi').checked && !document.querySelector('#tech-pytest').checked")
        for css in ("#tech-python", "#tech-fastapi", "#tech-pytest"):
            self.click(css)
        self.click("#next")
        self.click('input[name="agent"][value="codex"]')
        # Retour arriere vers la section projet, puis suggestion modifiable.
        self.click("#prev")
        self.click("#prev")
        self.click("#prev")
        self.js("document.querySelector('#architecture').closest('details').open = true")
        self.click("#architecture-suggest")
        self.wait("return document.querySelector('#architecture').value.includes('Couche HTTP')")
        self.js("const e=document.querySelector('#architecture'); e.value += '\\n- Module facturation isole.'; e.dispatchEvent(new Event('input',{bubbles:true}))")
        # Avertissements (description vide) : confirmation exigee avant validation.
        self.click('[data-goto="5"]')
        self.click("#check")
        self.wait("return !document.querySelector('#preview').hidden")
        self.click('[data-path="docs/ARCHITECTURE.md"]')
        self.assertIn("Module facturation isole.", self.js("return document.querySelector('#content').value"))
        self.assertTrue(self.js("return document.querySelector('#ack-warnings') !== null"))
        self.click("#validate-files")
        self.assertIn("avertissements", self.text("#status"))
        self.assertTrue(self.js("return document.querySelector('#download').disabled"))
        self.validate_files()
        self.wait("return !document.querySelector('#download').disabled")

if __name__ == "__main__":
    unittest.main()
