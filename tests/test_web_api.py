import http.client
import io
import json
import re
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from forge import web
from forge.verification import http as forge_http
from forge.verification.report import VerificationReport
from server import Handler, ThreadingHTTPServer

CONFIG = {
    "schema_version": 1, "name": "stock-api", "project_type": "api", "description": "API de stock",
    "technologies": ["python", "fastapi", "pytest"], "versions": {"python": "3.12"},
    "agents": ["codex", "claude"], "security": "strict", "options": {"mcp": False}, "architecture": "",
}
JSON_HEADERS = {"Content-Type": "application/json"}


class ApiServerTests(unittest.TestCase):
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

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def post(self, path, payload, headers=None):
        return self.request("POST", path, json.dumps(payload), dict(JSON_HEADERS, **(headers or {})))

    def test_pages_and_assets(self):
        for path in ("/", "/legacy", "/js/app.js", "/js/legacy.js", "/css/app.css"):
            status, headers, _ = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])

    def test_catalog(self):
        status, headers, body = self.request("GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        data = json.loads(body)
        python = [t for t in data["technologies"] if t["id"] == "python"][0]
        self.assertIn("3.13", python["versions"])
        self.assertEqual([a["id"] for a in data["agents"]], ["codex", "claude", "copilot"])
        self.assertIn("api", [p["id"] for p in data["project_types"]])

    def test_plan_preview_without_network(self):
        with mock.patch.object(forge_http._OPENER, "open", side_effect=AssertionError("reseau interdit")):
            status, _, body = self.post("/api/plan", {"config": CONFIG})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertIn("AGENTS.md", data["contents"])
        self.assertIn("CLAUDE.md", data["files"])
        self.assertIn("| Python | language | 3.12 |", data["contents"]["AGENTS.md"])
        self.assertIsNone(data["verification"])

    def test_plan_rejections(self):
        conflict = dict(CONFIG, technologies=["python", "flask", "django"])
        status, _, body = self.post("/api/plan", {"config": conflict})
        self.assertEqual(status, 422)
        self.assertIn("conflict", [d["code"] for d in json.loads(body)["diagnostics"]])
        for payload in ({"config": dict(CONFIG, name="../x")}, {"config": CONFIG, "verify": "yes"},
                        {"config": CONFIG, "shell": True}, {"verify": True}, [1]):
            status, _, body = self.post("/api/plan", payload)
            self.assertEqual(status, 400, payload)
            self.assertFalse(json.loads(body)["ok"])
        status, _, _ = self.request("POST", "/api/plan", "{", JSON_HEADERS)
        self.assertEqual(status, 400)

    def test_transport_guards(self):
        cases = [
            ({"Host": "attacker.example"}, 403),
            ({"Origin": "https://attacker.example"}, 403),
            ({"Origin": "null"}, 403),
            ({"Content-Type": "text/plain"}, 415),
        ]
        for headers, expected in cases:
            status, _, _ = self.post("/api/plan", {"config": CONFIG}, headers)
            self.assertEqual(status, expected, headers)
        status, _, _ = self.post("/api/plan", {"config": CONFIG}, {"Origin": "http://127.0.0.1:8765"})
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", "/api/plan", b"x" * 65537, JSON_HEADERS)
        self.assertEqual(status, 400)

    def test_archive(self):
        status, headers, content = self.post("/api/archive", {"config": CONFIG})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="stock-api.zip"')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            self.assertIn("stock-api/AGENTS.md", names)
            self.assertTrue(all(n.startswith("stock-api/") and ".." not in n for n in names))
        self.assertEqual(self.post("/api/archive", {"config": CONFIG})[2], content)
        status, _, body = self.post("/api/archive", {"config": dict(CONFIG, technologies=["python", "leftpadx"])})
        self.assertEqual(status, 422)
        self.assertFalse(json.loads(body)["ok"])

    def test_edited_preview_is_validated_and_archived(self):
        status, _, body = self.post("/api/plan", {"config": CONFIG})
        files = json.loads(body)["contents"]
        files["README.md"] = "# Contenu relu et modifie\n"

        status, _, body = self.post("/api/files/validate", {"config": CONFIG, "files": files})
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["modified"], ["README.md"])

        status, _, archive_body = self.post("/api/archive", {"config": CONFIG, "files": files})
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(archive_body)) as archive:
            self.assertEqual(archive.read("stock-api/README.md"), b"# Contenu relu et modifie\n")

    def test_edited_preview_rejects_path_and_file_set_changes(self):
        status, _, body = self.post("/api/plan", {"config": CONFIG})
        files = json.loads(body)["contents"]
        invalid = [
            {path: content for path, content in files.items() if path != "README.md"},
            dict(files, **{"extra.txt": "interdit"}),
            dict(files, **{"../escape": "interdit"}),
        ]
        for edited in invalid:
            with self.subTest(paths=edited.keys()):
                status, _, body = self.post("/api/files/validate", {"config": CONFIG, "files": edited})
                self.assertEqual(status, 400)
                self.assertFalse(json.loads(body)["ok"])

    def test_archive_revalidates_edited_file_set(self):
        status, _, body = self.post("/api/plan", {"config": CONFIG})
        files = json.loads(body)["contents"]
        files.pop("README.md")
        status, _, body = self.post("/api/archive", {"config": CONFIG, "files": files})
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["ok"])

    def test_archive_repeats_verification_and_blocks_errors(self):
        failing = VerificationReport((), (web.d.error("verification-package", "pypi:fastapi : inexistant"),))
        with mock.patch("forge.pipeline.verify_plan", return_value=failing):
            status, _, body = self.post("/api/archive", {"config": CONFIG, "verify": True})
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["diagnostics"][0]["code"], "verification-package")


    def test_unexpected_failure_returns_generic_500(self):
        with mock.patch("forge.web.run", side_effect=RuntimeError("detail interne /home/secret")):
            status, _, body = self.post("/api/plan", {"config": CONFIG})
        self.assertEqual(status, 500)
        self.assertNotIn(b"secret", body)


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("ui/index.html").read_text(encoding="utf-8")
        cls.js = Path("ui/js/app.js").read_text(encoding="utf-8")

    def test_no_inline_code_and_no_raw_html_injection(self):
        self.assertNotIn("<style", self.html)
        self.assertNotIn("<script>", self.html)
        self.assertNotIn(" style=", self.html)
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("insertAdjacentHTML", self.js)
        self.assertNotIn("eval(", self.js)

    def test_every_id_used_by_the_script_exists(self):
        ids = set(re.findall(r'id="([^"]+)"', self.html))
        used = set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", self.js))
        self.assertTrue(used)
        self.assertEqual(used - ids, set())

    def test_labels_point_to_existing_controls(self):
        ids = set(re.findall(r'id="([^"]+)"', self.html))
        for target in re.findall(r'<label for="([^"]+)"', self.html):
            self.assertIn(target, ids)

    def test_network_checks_are_opt_in(self):
        self.assertNotRegex(self.html, r'id="net-(verify|skills)"[^>]*checked')


if __name__ == "__main__":
    unittest.main()
