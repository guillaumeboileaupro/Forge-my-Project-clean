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


if __name__ == "__main__":
    unittest.main()
