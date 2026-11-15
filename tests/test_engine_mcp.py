"""Serveurs MCP optionnels (T15) : catalogue, pertinence, configurations, verification."""
import copy
import json
import re
import tomllib
import unittest

from forge import CATALOGS_DIR
from forge.config.answers import AnswersError, parse_answers
from forge.config.catalog import load_catalog
from forge.config.spec import SpecError, parse_spec
from forge.generator.render import generate
from forge.mcp.catalog import McpCatalogError, load_mcp_catalog, parse_server
from forge.pipeline import run
from forge.planner.plan import build_plan
from forge.verification.checks import check_mcp_server
from forge.verification.http import FetchError, Response
from forge.verification.report import verify_plan

WEB = {"name": "shop-web", "project_type": "web", "agents": ["claude", "codex", "copilot"],
       "technologies": ["node", "typescript", "react", "vitest"]}
API = {"name": "stock-api", "project_type": "api", "agents": ["codex"], "technologies": ["python", "fastapi", "pytest"]}
MCP_FILES = {".mcp.json", ".codex/config.toml", "docs/MCP.md"}
SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|Bearer [A-Za-z0-9])")


def files(spec):
    return generate(spec)[1]


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((CATALOGS_DIR / "mcp" / "servers.json").read_text(encoding="utf-8"))["servers"]

    def test_catalog_is_valid_and_pins_versions(self):
        servers = load_mcp_catalog()
        self.assertEqual(sorted(servers), ["github", "playwright"])
        playwright = servers["playwright"]
        self.assertIn("@playwright/mcp@%s" % playwright.package["version"], playwright.transport["args"])
        self.assertEqual(servers["github"].transport["headers"]["X-MCP-Readonly"], "true")

    def test_invalid_entries_are_refused(self):
        github, playwright = self.raw
        broken = [
            ("transport", "headers", {"Authorization": "Bearer abc"}),
            ("transport", "url", "http://api.example.com/mcp"),
            ("transport", "token_env", "lower-case"),
        ]
        for section, key, value in broken:
            raw = copy.deepcopy(github)
            raw[section][key] = value
            with self.assertRaises(McpCatalogError, msg=key):
                parse_server(raw)
        for args in (["-y", "@playwright/mcp@latest"], ["-y", "@playwright/mcp@0.0.85", "$(id)"]):
            raw = copy.deepcopy(playwright)
            raw["transport"]["args"] = args
            with self.assertRaises(McpCatalogError, msg=str(args)):
                parse_server(raw)
        raw = copy.deepcopy(playwright)
        raw["transport"]["command"] = "bash"
        with self.assertRaises(McpCatalogError):
            parse_server(raw)
        raw = copy.deepcopy(playwright)
        del raw["package"]
        with self.assertRaises(McpCatalogError):
            parse_server(raw)


class SelectionTests(unittest.TestCase):
    def test_nothing_is_generated_without_selection(self):
        for spec in (WEB, dict(WEB, options={"mcp": False}), API):
            self.assertFalse(MCP_FILES & set(files(spec)), spec["name"])

    def test_legacy_mcp_option_requires_an_explicit_selection(self):
        with self.assertRaisesRegex(SpecError, "mcp_servers"):
            parse_spec(dict(WEB, options={"mcp": True}))
        spec = parse_spec(dict(WEB, mcp_servers=["github"]))
        self.assertTrue(spec.options["mcp"])

    def test_configuration_per_agent(self):
        cases = {("claude",): {".mcp.json"}, ("copilot",): {".mcp.json"}, ("codex",): {".codex/config.toml"},
                 ("claude", "codex"): {".mcp.json", ".codex/config.toml"}}
        for agents, expected in cases.items():
            generated = set(files(dict(WEB, agents=list(agents), mcp_servers=["github"])))
            self.assertEqual(generated & MCP_FILES, expected | {"docs/MCP.md"}, agents)

    def test_shared_json_and_codex_toml(self):
        out = files(dict(WEB, mcp_servers=["github", "playwright"]))
        shared = json.loads(out[".mcp.json"])["mcpServers"]
        self.assertEqual(shared["github"]["headers"]["Authorization"], "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}")
        self.assertEqual(shared["github"]["headers"]["X-MCP-Toolsets"], "repos,issues,pull_requests,actions")
        self.assertEqual(shared["playwright"]["args"], ["-y", "@playwright/mcp@0.0.85", "--isolated", "--headless"])
        codex = tomllib.loads(out[".codex/config.toml"])["mcp_servers"]
        self.assertEqual(codex["github"]["bearer_token_env_var"], "GITHUB_PERSONAL_ACCESS_TOKEN")
        self.assertEqual(codex["github"]["http_headers"]["X-MCP-Readonly"], "true")
        self.assertEqual(codex["playwright"]["command"], "npx")
        self.assertEqual(set(shared), {"github", "playwright"})

    def test_no_secret_in_generated_files(self):
        out = files(dict(WEB, mcp_servers=["github", "playwright"]))
        for path in MCP_FILES:
            content = out[path].replace("Bearer ${", "")
            self.assertIsNone(SECRET.search(content), path)

    def test_only_relevant_servers_are_accepted(self):
        plan = run(dict(WEB, mcp_servers=["github"])).plan
        self.assertTrue(plan.ok)
        with self.assertRaisesRegex(Exception, "Plan invalide"):
            run(dict(API, mcp_servers=["playwright"]))
        with self.assertRaisesRegex(Exception, "Plan invalide"):
            run(dict(API, mcp_servers=["inexistant"]))
        catalog = load_catalog()
        with self.assertRaisesRegex(AnswersError, "non pertinent"):
            parse_answers({"project_type": "api", "mcp_servers": ["playwright"]}, catalog)
        with self.assertRaisesRegex(AnswersError, "inconnu"):
            parse_answers({"mcp_servers": ["inexistant"]}, catalog)
        self.assertEqual(parse_answers({"project_type": "web", "mcp_servers": ["playwright"]}, catalog)["mcp_servers"],
                         ["playwright"])

    def test_runtime_warning_and_unverified_warning(self):
        python_web = {"name": "site-django", "project_type": "web", "agents": ["claude"],
                      "technologies": ["python", "django", "pytest"], "mcp_servers": ["playwright"]}
        codes = [x.code for x in run(python_web).diagnostics]
        self.assertIn("mcp-runtime", codes)
        self.assertIn("mcp-unverified", codes)
        self.assertIn("NON VERIFIE", run(python_web).files["docs/MCP.md"])


def registry_entry(name="io.github.microsoft/playwright-mcp", repository="https://github.com/microsoft/playwright-mcp",
                   status="active", packages=("@playwright/mcp",), remotes=()):
    return {"server": {"name": name, "version": "0.0.85", "repository": {"url": repository, "source": "github"},
                       "packages": [{"registryType": "npm", "identifier": p} for p in packages],
                       "remotes": [{"type": "streamable-http", "url": u} for u in remotes]},
            "_meta": {"io.modelcontextprotocol.registry/official": {"status": status, "isLatest": True}}}


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.servers = load_mcp_catalog()

    def check(self, server_id, response):
        def fetch(url, payload=None):
            self.assertTrue(url.startswith("https://registry.modelcontextprotocol.io/v0/servers/"))
            if isinstance(response, Exception):
                raise response
            return response
        return check_mcp_server(self.servers[server_id], fetch)

    def test_registry_statuses(self):
        self.assertEqual(self.check("playwright", Response(200, registry_entry())).status.value, "PASS")
        github = registry_entry("io.github.github/github-mcp-server", "https://github.com/github/github-mcp-server",
                                packages=(), remotes=("https://api.githubcopilot.com/mcp/",))
        self.assertEqual(self.check("github", Response(200, github)).status.value, "PASS")
        failures = [Response(404, None), Response(200, registry_entry(repository="https://github.com/evil/fork")),
                    Response(200, registry_entry(status="deprecated")), Response(200, registry_entry(packages=("other",)))]
        for response in failures:
            self.assertEqual(self.check("playwright", response).status.value, "FAIL")
        self.assertEqual(self.check("playwright", FetchError("hors ligne")).status.value, "NON VERIFIE")

    def test_failed_provenance_blocks_generation(self):
        def fetch(url, payload=None):
            if "modelcontextprotocol" in url:
                return Response(200, registry_entry(repository="https://github.com/evil/fork"))
            raise FetchError("hors ligne")
        report = verify_plan(build_plan(dict(WEB, mcp_servers=["playwright"])), fetch, today="2026-11-15")
        self.assertIn("verification-mcp", [x.code for x in report.diagnostics if x.severity.value == "error"])
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
