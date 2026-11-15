"""Hooks Git et hooks d'agents generes (T14) : tests fonctionnels sur de vrais depots."""
import io
import json
import os
import random
import shutil
import stat
import string
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from forge.generator.archive import build_zip
from forge.pipeline import run

PY = {"name": "hook-demo", "project_type": "library", "agents": ["codex", "claude", "copilot"],
      "technologies": ["python", "unittest"]}
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@localhost", "GIT_CONFIG_NOSYSTEM": "1"}


def fake_token():
    return "ghp" + "_" + "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(36))


class AgentGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.guard = Path(cls.dir, "agent_guard.py")
        cls.guard.write_text(run(PY).files["scripts/hooks/agent_guard.py"], encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def decide(self, payload):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        done = subprocess.run([sys.executable, str(self.guard)], input=raw, capture_output=True, text=True, check=False)
        return done.returncode, done.stderr

    def test_blocks_hook_bypass_for_every_agent_format(self):
        payloads = [
            {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m 'x'"}},  # Claude Code
            {"tool_name": "Bash", "tool_input": {"command": ["bash", "-lc", "git commit -nm x"]}},  # Codex
            {"toolName": "bash", "toolArgs": json.dumps({"command": "git push -f origin main"})},  # Copilot
            {"tool_name": "Bash", "tool_input": {"command": "git push origin +main"}},
            {"tool_name": "Bash", "tool_input": {"command": "git config core.hooksPath /dev/null"}},
            {"tool_name": "Bash", "tool_input": {"command": "npm test && git push --force"}},
        ]
        for payload in payloads:
            code, message = self.decide(payload)
            self.assertEqual(code, 2, payload)
            self.assertIn("action refusee", message)

    def test_blocks_secret_files(self):
        payloads = [
            {"tool_name": "Write", "tool_input": {"file_path": "/repo/.env", "content": "A=1"}},
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/certs/server.key"}},
            {"tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: .env.local\n+A=1\n*** End Patch"}},
            {"toolName": "create", "toolArgs": json.dumps({"path": "/repo/id_ed25519"})},
        ]
        for payload in payloads:
            self.assertEqual(self.decide(payload)[0], 2, payload)

    def test_allows_normal_work(self):
        payloads = [
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'feat: x' && git push --force-with-lease"}},
            {"tool_name": "Bash", "tool_input": {"command": "python -m pytest -n auto"}},
            {"tool_name": "Write", "tool_input": {"file_path": "/repo/.env.example", "content": "API_KEY="}},
            {"tool_name": "Write", "tool_input": {"file_path": "/repo/src/env.py", "content": "load('.env')"}},
            {"toolName": "view", "toolArgs": json.dumps({"path": ".env"})},
            {"tool_name": "Read", "tool_input": {"file_path": "/repo/.env"}},
        ]
        for payload in payloads:
            self.assertEqual(self.decide(payload)[0], 0, payload)

    def test_unreadable_event_is_refused(self):
        for raw in ("", "not json", "[1, 2]"):
            self.assertEqual(self.decide(raw)[0], 2, raw)


class AgentConfigTests(unittest.TestCase):
    def test_configs_follow_documented_schemas_and_selected_agents(self):
        files = run(PY).files
        claude = json.loads(files[".claude/settings.json"])["hooks"]["PreToolUse"][0]
        self.assertEqual(claude["hooks"][0]["type"], "command")
        self.assertIn("$CLAUDE_PROJECT_DIR/scripts/hooks/agent_guard.py", claude["hooks"][0]["command"])
        codex = json.loads(files[".codex/hooks.json"])["hooks"]["PreToolUse"][0]
        self.assertEqual(codex["matcher"], "^(Bash|apply_patch)$")
        self.assertIn("git rev-parse --show-toplevel", codex["hooks"][0]["command"])
        copilot = json.loads(files[".github/hooks/forge-guard.json"])
        self.assertEqual(copilot["version"], 1)
        self.assertEqual(copilot["hooks"]["preToolUse"][0]["type"], "command")
        only_codex = run(dict(PY, agents=["codex"])).files
        self.assertNotIn(".claude/settings.json", only_codex)
        self.assertNotIn(".github/hooks/forge-guard.json", only_codex)
        self.assertIn(".codex/hooks.json", only_codex)

    def test_hooks_are_documented(self):
        files = run(PY).files
        self.assertIn("git config core.hooksPath .githooks", files["AGENTS.md"])
        self.assertIn("/hooks", files["AGENTS.md"])
        self.assertIn("git config core.hooksPath .githooks", files["CONTRIBUTING.md"])

    def test_scripts_are_executable_in_archive(self):
        files = run(PY).files
        with zipfile.ZipFile(io.BytesIO(build_zip("hook-demo", files))) as archive:
            modes = {i.filename: stat.S_IMODE(i.external_attr >> 16) for i in archive.infolist()}
        for name in (".githooks/pre-commit", ".githooks/commit-msg", ".githooks/pre-push", "scripts/hooks/agent_guard.py"):
            self.assertEqual(modes["hook-demo/" + name], 0o755, name)
        self.assertEqual(modes["hook-demo/AGENTS.md"], 0o644)

    def test_no_redundant_checks_between_stages(self):
        files = run(dict(PY, technologies=["python", "pytest", "ruff", "mypy", "pip-audit"])).files
        pre_commit, pre_push = files[".githooks/pre-commit"], files[".githooks/pre-push"]
        self.assertIn("ruff check .", pre_commit)
        self.assertNotIn("pytest", pre_commit)
        self.assertIn("python -m pytest", pre_push)
        self.assertNotIn("ruff", pre_push)
        for hook in (pre_commit, pre_push):
            self.assertNotIn("pip-audit", hook)  # audits : CI uniquement


class GitHookFunctionalTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.files = run(dict(PY, technologies=["python", "unittest"])).files
        for path, content in self.files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            if path.startswith((".githooks/", "scripts/hooks/")):
                target.chmod(0o755)
        self.env = dict(os.environ, **GIT_ENV)
        self.env["PATH"] = os.pathsep.join(p for p in self.env["PATH"].split(os.pathsep)
                                           if not (Path(p) / "gitleaks").exists())  # chemin de repli teste
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.hooksPath", ".githooks")
        # Pas de maintenance Git detachee : elle courrait avec la suppression du dossier (CI instable).
        self.git("config", "gc.auto", "0")
        self.git("config", "maintenance.auto", "false")

    def git(self, *args, check=True, env=None):
        return subprocess.run(["git", *args], cwd=self.root, env=env or self.env, capture_output=True, text=True, check=check)

    def commit(self, message, env=None):
        self.git("add", "-A")
        return self.git("commit", "-q", "-m", message, check=False, env=env)

    def test_valid_commit_passes(self):
        done = self.commit("feat: initialisation du projet")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_commit_message_must_be_conventional(self):
        done = self.commit("mise a jour")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Conventional Commits", done.stderr)

    def test_sensitive_file_and_secret_pattern_are_blocked(self):
        (self.root / ".env").write_text("API_KEY=x\n", encoding="utf-8")
        self.assertEqual(self.git("status", "--porcelain", ".env").stdout, "")  # deja ignore par .gitignore
        self.git("add", "-f", ".env")  # ajout force : le hook doit encore bloquer
        done = self.commit("feat: config")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("fichier sensible indexe", done.stderr)
        self.assertIn("NON VERIFIE", done.stderr)
        self.git("rm", "-q", "--cached", ".env")
        (self.root / ".env").unlink()
        (self.root / "settings.txt").write_text("token=%s\n" % fake_token(), encoding="utf-8")
        done = self.commit("feat: settings")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("motif de secret", done.stderr)
        (self.root / "settings.txt").write_text("token=\n", encoding="utf-8")
        (self.root / ".env.example").write_text("API_KEY=\n", encoding="utf-8")
        self.assertEqual(self.commit("feat: settings").returncode, 0)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks absent")
    def test_gitleaks_branch_when_installed(self):
        env = dict(self.env, PATH=os.pathsep.join([str(Path(shutil.which("gitleaks")).parent), self.env["PATH"]]))
        (self.root / "settings.txt").write_text("token=%s\n" % fake_token(), encoding="utf-8")
        done = self.commit("feat: settings", env=env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("gitleaks", done.stderr)

    def test_missing_tool_fails_with_explanation(self):
        files = run(dict(PY, technologies=["python", "unittest", "ruff"])).files
        (self.root / ".githooks" / "pre-commit").write_text(files[".githooks/pre-commit"], encoding="utf-8")
        env = dict(self.env, PATH="/usr/bin:/bin")
        if shutil.which("ruff", path=env["PATH"]):
            self.skipTest("ruff installe dans le systeme")
        done = self.commit("feat: x", env=env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("ruff introuvable", done.stderr)

    def test_pre_push_runs_tests_and_blocks_failures(self):
        env = dict(self.env, PYTHONPATH=str(self.root / "src"), PATH=os.path.dirname(sys.executable) + os.pathsep + self.env["PATH"])
        python_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, python_dir)
        (python_dir / "python").symlink_to(sys.executable)  # le hook appelle `python`
        env["PATH"] = str(python_dir) + os.pathsep + env["PATH"]
        hook = str(self.root / ".githooks" / "pre-push")
        ok = subprocess.run([hook], cwd=self.root, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        (self.root / "tests" / "test_broken.py").write_text(
            "import unittest\n\n\nclass Broken(unittest.TestCase):\n    def test_fail(self) -> None:\n        self.fail()\n",
            encoding="utf-8")
        ko = subprocess.run([hook], cwd=self.root, env=env, capture_output=True, text=True, check=False)
        self.assertNotEqual(ko.returncode, 0)
        self.assertIn("Tests et couverture (unittest (bibliotheque standard)) en echec", ko.stderr)


if __name__ == "__main__":
    unittest.main()
