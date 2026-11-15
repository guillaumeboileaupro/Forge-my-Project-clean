import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from forge.__main__ import main
from forge.config.catalog import load_catalog
from forge.generator.paths import safe_relative_path
from forge.generator.render import generate
from forge.rules.engine import load_rules

PYTHON_API = {
    "name": "stock-api", "project_type": "api", "agents": ["codex", "claude"],
    "description": "API de gestion de stock.",
    "technologies": ["python", "fastapi", "pytest", "pytest-cov", "ruff", "pip-audit", "docker"],
    "security": "hardened",
}
TS_WEB = {
    "name": "shop-web", "project_type": "web", "agents": ["copilot"],
    "description": "Boutique en ligne.", "technologies": ["typescript", "node", "react", "vitest", "eslint", "npm-audit"],
}
SCAFFOLD = {
    ".github/workflows/ci.yml", ".gitignore", "pyproject.toml", "src/stock_api/__init__.py", "tests/test_smoke.py",
    "package.json", "tsconfig.json", "src/index.ts", "src/index.js", "eslint.config.js", "vitest.config.js",
    "tests/smoke.test.ts", "tests/smoke.test.js",
}
HOOKS = {".githooks/pre-commit", ".githooks/commit-msg", ".githooks/pre-push", "scripts/hooks/agent_guard.py"}
AGENT_HOOK_FILES = {".claude/settings.json", ".codex/hooks.json", ".github/hooks/forge-guard.json"}
MCP_FILES = {".mcp.json", ".codex/config.toml"}  # uniquement si des serveurs MCP sont choisis
SCAFFOLD = SCAFFOLD | HOOKS | AGENT_HOOK_FILES | MCP_FILES
BASE_DOCS = {
    "AGENTS.md", "README.md", "SECURITY.md", "CONTRIBUTING.md", "TODO.md", "docs/ARCHITECTURE.md",
    "docs/DEVELOPMENT_PLAN.md", "docs/TESTING.md", "docs/DEPENDENCIES.md", "docs/adr/0001-choix-techniques.md",
}


class RepositoryRulesTests(unittest.TestCase):
    def test_rules_and_templates_load(self):
        rules = load_rules(load_catalog())
        self.assertEqual([r.id for r in rules if r.mandatory], ["base"])

    def test_every_output_is_safe_documentation_without_business_code(self):
        for spec in (PYTHON_API, TS_WEB, dict(TS_WEB, mcp_servers=["github", "playwright"])):
            _, files = generate(spec)
            for path, content in files.items():
                safe_relative_path(path)
                self.assertTrue(path.endswith(".md") or path in SCAFFOLD, path)
                self.assertNotIn("{{", content.replace("{{ secret }}", ""), path)
                self.assertTrue(content.endswith("\n") and content.strip(), path)


class ScaffoldTests(unittest.TestCase):
    def test_code_files_are_empty_entry_points_and_smoke_tests_only(self):
        _, files = generate(PYTHON_API)
        self.assertEqual(files["src/stock_api/__init__.py"].count("\n"), 1)
        self.assertNotIn("def ", files["src/stock_api/__init__.py"])
        _, ts = generate(TS_WEB)
        self.assertEqual([l for l in ts["src/index.ts"].splitlines() if not l.startswith("//")], ["export {};"])

    def test_workflow_is_pinned_and_least_privilege(self):
        _, files = generate(PYTHON_API)
        workflow = files[".github/workflows/ci.yml"]
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        for line in workflow.splitlines():
            if "uses:" in line:
                self.assertRegex(line, r"uses: actions/[a-z-]+@[0-9a-f]{40} # v\d")
        self.assertIn('python-version: "3.13"', workflow)
        for command in ('python -m pip install -e ".[dev]"', "ruff check .", "python -m pytest"):
            self.assertIn("          " + command + "\n", workflow)
        quality, security = workflow.split("\n  security:\n")
        self.assertNotIn("pip-audit", quality)  # audit execute une seule fois, dans le job security
        self.assertIn("pip-audit --strict --no-deps --disable-pip", security)
        self.assertNotIn("docker build", workflow)

    def test_manifests_follow_selection_and_verification(self):
        _, files = generate(PYTHON_API)
        pyproject = files["pyproject.toml"]
        self.assertIn('requires-python = ">=3.13"', pyproject)
        self.assertIn('  "fastapi",', pyproject)
        self.assertIn("--cov-fail-under=80", pyproject)
        _, ts = generate(TS_WEB)
        package = json.loads(ts["package.json"])
        self.assertEqual(package["scripts"]["test"], "vitest run")
        self.assertEqual(package["devDependencies"]["typescript-eslint"], "latest")
        self.assertIn("typescript-eslint", ts["docs/DEPENDENCIES.md"])

    def test_javascript_only_stack(self):
        _, files = generate(dict(TS_WEB, technologies=["javascript", "node", "node-test", "eslint"]))
        self.assertIn("src/index.js", files)
        self.assertIn("tests/smoke.test.js", files)
        self.assertNotIn("tsconfig.json", files)
        self.assertNotIn("typescript-eslint", files["eslint.config.js"])
        self.assertEqual(json.loads(files["package.json"])["scripts"]["test"], "node --test")


class PythonApiDocumentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.files = generate(PYTHON_API)

    def test_expected_files(self):
        self.assertEqual(set(self.files), BASE_DOCS | HOOKS | {
            "CLAUDE.md", "docs/DEPLOYMENT.md", ".github/workflows/ci.yml", ".gitignore", "pyproject.toml",
            "src/stock_api/__init__.py", "tests/test_smoke.py", ".claude/settings.json", ".codex/hooks.json"})

    def test_agents_md_is_specific(self):
        agents = self.files["AGENTS.md"]
        for expected in (
            "API de gestion de stock.", "`python -m pytest`", "`ruff check .`", "`pip-audit`", "Codex", "Claude Code",
            "Couche HTTP", "python-project-quality", "Revue de securite independante", "## Definition of Done",
            "## Workflow Git", "## Erreurs frequentes", "| Python | language | 3.13 |",
        ):
            self.assertIn(expected, agents)
        for absent in ("npm", "Copilot", "typescript-no-any"):
            self.assertNotIn(absent, agents)

    def test_claude_imports_agents(self):
        self.assertIn("@AGENTS.md", self.files["CLAUDE.md"])

    def test_dependencies_are_unverified_until_checked(self):
        deps = self.files["docs/DEPENDENCIES.md"]
        self.assertIn("| fastapi | pypi | execution | NON VERIFIE | NON VERIFIE | NON VERIFIE |", deps)
        self.assertIn("| pytest | pypi | developpement | NON VERIFIE | NON VERIFIE | NON VERIFIE |", deps)
        self.assertNotIn("PASS |", deps)

    def test_todo_has_tracking_columns_and_no_invented_estimate(self):
        todo = self.files["TODO.md"]
        self.assertIn("| Estime | Reel | Ecart |", todo)
        self.assertIn("a estimer", todo)
        self.assertIn("Couche domaine", todo)

    def test_rendering_is_deterministic(self):
        self.assertEqual(generate(PYTHON_API)[1], self.files)


class TypeScriptWebDocumentsTests(unittest.TestCase):
    def test_typescript_web_documents(self):
        _, files = generate(TS_WEB)
        self.assertEqual(set(files) - SCAFFOLD, BASE_DOCS | {".github/copilot-instructions.md"})
        self.assertTrue({"package.json", "tsconfig.json", "src/index.ts", "tests/smoke.test.ts"} <= set(files))
        agents = files["AGENTS.md"]
        self.assertIn("`npx vitest run`", agents)
        self.assertIn("aucun any", agents)
        self.assertIn("ui-ux-accessibility", agents)
        self.assertNotIn("pyproject", agents)

    def test_optional_outputs_require_opt_in(self):
        self.assertNotIn("docs/MCP.md", generate(TS_WEB)[1])
        self.assertIn("docs/MCP.md", generate(dict(TS_WEB, mcp_servers=["github", "playwright"]))[1])


class MissingInformationTests(unittest.TestCase):
    def test_unknown_commands_and_architecture_are_explicit(self):
        spec = {"name": "bare-lib", "project_type": "library", "agents": ["codex"], "technologies": ["python"],
                "architecture": "Module unique {{ secret }}"}
        plan, files = generate(spec)
        codes = {x.code for x in plan.diagnostics}
        self.assertTrue({"unknown-command", "description-empty"} <= codes)
        self.assertIn("Tests : `NON DEFINI`", files["docs/TESTING.md"])
        self.assertIn("Module unique {{ secret }}", files["docs/ARCHITECTURE.md"])
        self.assertIn("Suggestions des regles locales", files["docs/ARCHITECTURE.md"])
        self.assertIn("Aucune dependance tierce", files["docs/DEPENDENCIES.md"])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(list(args))
        return code, out.getvalue()

    def test_plan_and_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp, "good.json")
            good.write_text(json.dumps(PYTHON_API), encoding="utf-8")
            code, out = self.run_cli("plan", str(good))
            self.assertEqual(code, 0)
            self.assertIn("AGENTS.md", json.loads(out)["files"])
            code, out = self.run_cli("show", str(good), "CLAUDE.md")
            self.assertEqual(code, 0)
            self.assertIn("@AGENTS.md", out)
            bad = Path(tmp, "bad.json")
            bad.write_text(json.dumps(dict(PYTHON_API, technologies=["python", "flask", "django"])), encoding="utf-8")
            code, out = self.run_cli("plan", str(bad))
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out)["diagnostics"][0]["code"], "conflict")


if __name__ == "__main__":
    unittest.main()
