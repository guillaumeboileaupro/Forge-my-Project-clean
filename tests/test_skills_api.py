"""Integration HTTP de l'approbation des skills externes (T10).

GitHub est remplace par le faux client des tests du moteur : aucune requete
reseau n'est emise. Le parcours couvre recherche, approbation, conservation
(brouillon, import/export, profil), verification et refus d'un skill modifie.
"""
import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from server import Handler, ThreadingHTTPServer
from tests.test_engine_external_skills import CONFIG as SKILL_CONFIG
from tests.test_engine_external_skills import FakeClient, FakeGh, modified_repos

CONFIG = {
    "schema_version": 1, "name": "shop-web", "project_type": "web", "description": "",
    "technologies": ["typescript", "node", "react", "vitest"], "agents": ["claude"],
}
HEADERS = {"Content-Type": "application/json"}


class SkillsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.client = FakeGh()
        patches = [
            mock.patch("forge.skills.service.default_client", lambda: self.client),
            mock.patch("forge.skills.service.b.load_copy_policy", lambda: SKILL_CONFIG),
        ]
        self.tmp = tempfile.TemporaryDirectory()
        patches.append(mock.patch.dict(os.environ, {"FORGE_PROFILES_FILE": os.path.join(self.tmp.name, "p.json")}))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def post(self, path, payload, headers=None, method="POST"):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path, json.dumps(payload), dict(HEADERS, **(headers or {})))
        response = connection.getresponse()
        status, body = response.status, response.read()
        connection.close()
        return status, body

    def post_json(self, path, payload):
        status, body = self.post(path, payload)
        return status, json.loads(body)

    def approval(self, name):
        status, data = self.post_json("/api/skills/search", {"config": CONFIG})
        self.assertEqual(status, 200)
        return [c for c in data["candidates"] if c["name"] == name][0]["approval"]

    def test_search_shows_provenance_and_commit(self):
        status, data = self.post_json("/api/skills/search", {"config": CONFIG})
        self.assertEqual(status, 200)
        first = data["candidates"][0]
        for key in ("name", "description", "repository", "commit", "source", "recognized", "digest",
                    "copied_files", "ignored_files", "notes", "approval"):
            self.assertIn(key, first)
        self.assertEqual((first["name"], first["repository"], first["recognized"]),
                         ("webapp-testing", "anthropics/skills", True))
        self.assertEqual(len(first["commit"]), 40)
        self.assertEqual([(c["name"], c["recognized"]) for c in data["candidates"]][1], ("react-helper", False))

    def test_search_refuses_invalid_requests(self):
        for payload in ({"config": dict(CONFIG, name="X")}, {"config": dict(CONFIG, technologies=["django", "react"])},
                        {"config": CONFIG, "extra": 1}, {}):
            status, data = self.post_json("/api/skills/search", payload)
            self.assertIn(status, (400, 422), payload)
            self.assertFalse(data["ok"])
        status, _ = self.post("/api/skills/search", {"config": CONFIG}, {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_verify_approvals(self):
        intact, changed = self.approval("webapp-testing"), self.approval("react-helper")
        self.client = FakeGh(repos=modified_repos("skills/react-helper/SKILL.md", "modifie"))
        status, data = self.post_json("/api/skills/verify", {"approvals": [intact, changed]})
        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertEqual([c["status"] for c in data["checks"]], ["PASS", "FAIL"])
        status, data = self.post_json("/api/skills/verify", {"approvals": [dict(intact, digest="x")]})
        self.assertEqual(status, 400)
        self.assertIn("empreinte invalide", data["error"])

    def test_approvals_survive_export_import_and_profiles(self):
        approval = self.approval("webapp-testing")
        answers = dict(CONFIG, external_skills=[approval])
        answers.pop("schema_version")
        status, data = self.post_json("/api/answers/validate", {"document": answers})
        self.assertEqual(status, 200)
        exported = data["export"]
        status, data = self.post_json("/api/answers/validate", {"document": exported})
        self.assertEqual(data["answers"]["external_skills"], [approval])
        legacy = dict(answers, external_skills=[{k: v for k, v in approval.items() if k != "digest"}])
        status, data = self.post_json("/api/answers/validate", {"document": legacy})
        self.assertEqual(status, 400)
        self.assertIn("approuver a nouveau", data["error"])
        status, data = self.post_json("/api/profiles", {"label": "Web", "description": "", "answers": answers})
        self.assertEqual(status, 201)
        self.assertEqual(data["profile"]["answers"]["external_skills"], [approval])

    def test_generation_copies_approved_skill_and_blocks_modified_one(self):
        approval = self.approval("webapp-testing")
        request = {"config": dict(CONFIG, external_skills=[approval]), "skills": True}
        status, data = self.post_json("/api/plan", request)
        self.assertEqual(status, 200)
        self.assertIn(".claude/skills/webapp-testing/SKILL.md", data["files"])
        self.assertFalse([p for p in data["files"] if p.endswith(".py") and "skills/" in p])
        self.client = FakeClient(repos=modified_repos("skills/webapp-testing/SKILL.md", "change"))
        status, data = self.post_json("/api/plan", request)
        self.assertFalse(data["ok"])
        self.assertIn("skill-modified", [x["code"] for x in data["diagnostics"]])
        status, data = self.post_json("/api/archive", request)
        self.assertEqual(status, 422)


    # --- Interactions T10 / T15 / T16 : apercu edite, skills approuves, MCP ---
    def edited_request(self):
        approval = self.approval("webapp-testing")
        config = dict(CONFIG, agents=["claude", "codex"], external_skills=[approval], mcp_servers=["github", "playwright"])
        request = {"config": config, "skills": True}
        status, data = self.post_json("/api/plan", request)
        self.assertEqual(status, 200, data)
        files = data["contents"]
        for path in (".claude/skills/webapp-testing/SKILL.md", ".mcp.json", ".codex/config.toml", "docs/MCP.md"):
            self.assertIn(path, files)
        return request, files

    def test_edited_preview_keeps_approved_skill_and_mcp_in_archive(self):
        import io
        import zipfile
        request, files = self.edited_request()
        generated_mcp = files[".mcp.json"]
        files["AGENTS.md"] += "\nRelu dans l'editeur.\n"
        files[".claude/skills/webapp-testing/SKILL.md"] += "\nNote locale.\n"
        status, data = self.post_json("/api/files/validate", dict(request, files=files))
        self.assertEqual(status, 200, data)
        self.assertEqual(data["modified"], [".claude/skills/webapp-testing/SKILL.md", "AGENTS.md"])
        status, body = self.post("/api/archive", dict(request, files=files))
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            read = lambda path: archive.read("shop-web/" + path).decode("utf-8")
            self.assertTrue(read("AGENTS.md").endswith("Relu dans l'editeur.\n"))
            self.assertTrue(read(".claude/skills/webapp-testing/SKILL.md").endswith("Note locale.\n"))
            self.assertEqual(read(".mcp.json"), generated_mcp)
            self.assertFalse([n for n in archive.namelist() if "skills/" in n and n.endswith(".py")])

    def test_edits_do_not_outlive_a_changed_skill_or_mcp_selection(self):
        request, files = self.edited_request()
        config = request["config"]
        for changed in (dict(config, mcp_servers=[]), dict(config, external_skills=[]),
                        dict(config, agents=["claude"])):
            with self.subTest(changed=changed):
                status, data = self.post_json("/api/archive", dict(request, config=changed, files=files))
                self.assertEqual(status, 400)
                self.assertIn("inattendus", data["error"])
        self.client = FakeClient(repos=modified_repos("skills/webapp-testing/SKILL.md", "change"))
        status, data = self.post_json("/api/archive", dict(request, files=files))
        self.assertEqual(status, 422)
        self.assertIn("skill-modified", [x["code"] for x in data["diagnostics"]])

    def test_editor_cannot_inject_unselected_skill_or_mcp_file(self):
        status, data = self.post_json("/api/plan", {"config": CONFIG})
        files = data["contents"]
        for extra in (".mcp.json", ".codex/config.toml", ".claude/skills/evil/SKILL.md"):
            with self.subTest(extra=extra):
                status, data = self.post_json("/api/files/validate", {"config": CONFIG, "files": dict(files, **{extra: "{}"})})
                self.assertEqual(status, 400)
                status, data = self.post_json("/api/archive", {"config": CONFIG, "files": dict(files, **{extra: "{}"})})
                self.assertEqual(status, 400)

    def test_local_write_preserves_approved_skill_and_mcp(self):
        import tempfile as tf
        request, files = self.edited_request()
        with tf.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"FORGE_WRITE_ROOT": tmp}):
            dest = os.path.join(os.path.realpath(tmp), "shop-web")
            status, data = self.post_json("/api/write/compare", dict(request, files=files, destination=dest))
            self.assertEqual(status, 200, data)
            status, data = self.post_json("/api/write/apply", dict(request, files=files, destination=dest,
                                                                   token=data["token"], decisions={}, confirm=True))
            self.assertEqual(status, 200, data)
            for path in (".claude/skills/webapp-testing/SKILL.md", ".mcp.json", ".codex/config.toml"):
                with open(os.path.join(dest, path), encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), files[path])
            copied = [n for _, _, names in os.walk(os.path.join(dest, ".claude/skills")) for n in names]
            self.assertFalse([n for n in copied if n.endswith(".py")])
            # Un skill modifie depuis l'approbation bloque l'ecriture comme l'archive.
            self.client = FakeClient(repos=modified_repos("skills/webapp-testing/SKILL.md", "change"))
            status, data = self.post_json("/api/write/compare", dict(request, files=files, destination=dest))
            self.assertEqual(status, 422)
            self.assertIn("skill-modified", [x["code"] for x in data["diagnostics"]])

if __name__ == "__main__":
    unittest.main()
