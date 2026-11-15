import copy
import unittest

from forge.config.spec import SpecError, parse_spec
from forge.pipeline import run
from forge.planner.plan import build_plan
from forge.skills import bundle
from forge.skills.external import keywords_for_plan, search
from forge.skills.github import GhCliClient
from forge.skills.service import skills_for_plan, verify_approvals
from forge.verification.http import FetchError

SHA_A, SHA_B = "a" * 40, "b" * 40
HEADER = "---\nname: {name}\ndescription: {description}\n---\n"
REPOS = {
    "anthropics/skills": (SHA_A, {
        "skills/webapp-testing/SKILL.md": HEADER.format(name="webapp-testing", description="Test React web apps"),
        "skills/webapp-testing/run.py": "print()",
        "skills/pdf/SKILL.md": HEADER.format(name="pdf", description="PDF files"),
    }),
    "stranger/agent-stuff": (SHA_B, {
        "skills/react-helper/SKILL.md": HEADER.format(name="react-helper", description="React components"),
    }),
    "owner/my-skills": (SHA_A, {}),
}
CONFIG = {
    "my_skills": {"repository": "owner/my-skills", "ref": "main", "path": "skills"},
    "copy": bundle.load_copy_policy()["copy"],
    "external_catalogs": [{"label": "Anthropic", "repository": "anthropics/skills", "ref": "main", "path": "skills"}],
    "search": {"github_code_search": True, "max_candidates": 20},
}
SPEC = {"name": "shop-web", "project_type": "web", "agents": ["claude"],
        "technologies": ["typescript", "node", "react", "vitest"]}


class FakeClient:
    """Faux GitHub : arborescence avec SHA de blobs reels ; `tamper` falsifie le contenu servi."""

    def __init__(self, offline=(), repos=None, tamper=None):
        self.offline = set(offline)
        self.repos = repos or REPOS
        self.tamper = tamper or {}

    def get_json(self, api_path):
        if api_path.startswith("/search/code"):
            return {"items": [{"repository": {"full_name": "stranger/agent-stuff"}, "path": "skills/react-helper/SKILL.md"},
                              {"repository": {"full_name": "root/skill"}, "path": "SKILL.md"}]}
        repository = "/".join(api_path.split("/")[2:4])
        if repository in self.offline or repository not in self.repos:
            raise FetchError("indisponible")
        sha, files = self.repos[repository]
        if "/commits/" in api_path:
            return {"sha": sha}
        return {"tree": [{"path": p, "mode": "100644", "type": "blob", "size": len(c.encode()),
                          "sha": bundle.git_blob_sha(c)} for p, c in files.items()]}

    def get_text(self, repository, path, sha):
        return self.tamper.get(path, self.repos[repository][1][path])


class FakeGh(FakeClient, GhCliClient):
    pass


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_plan(SPEC)

    def test_keywords_come_from_the_configuration(self):
        self.assertEqual(keywords_for_plan(self.plan), ["node", "react", "typescript", "vitest", "web"])

    def test_recognized_catalog_candidates_only_without_gh(self):
        result = search(keywords_for_plan(self.plan), FakeClient(), CONFIG)
        self.assertEqual([c.name for c in result.candidates], ["webapp-testing"])
        candidate = result.candidates[0]
        self.assertTrue(candidate.recognized)
        approval = candidate.approval()
        self.assertEqual({k: approval[k] for k in ("repository", "commit", "path", "name")},
                         {"repository": "anthropics/skills", "commit": SHA_A, "path": "skills", "name": "webapp-testing"})
        self.assertRegex(approval["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertIn("run.py", candidate.ignored_files[0])
        self.assertIn("NON VERIFIEE", " ".join(result.notes))

    def test_github_search_marks_unrecognized_sources(self):
        result = search(keywords_for_plan(self.plan), FakeGh(), CONFIG)
        names = [(c.name, c.recognized) for c in result.candidates]
        self.assertEqual(names, [("webapp-testing", True), ("react-helper", False)])
        self.assertIn("Source non reconnue", result.candidates[1].notes[0])

    def test_unavailable_catalog_is_reported(self):
        result = search(["react"], FakeClient(offline={"anthropics/skills"}), CONFIG)
        self.assertEqual(result.candidates, [])
        self.assertIn("anthropics/skills NON VERIFIE", " ".join(result.notes))


def approval_for(name, client=None):
    """Approbation telle que l'interface l'enregistre a partir d'un candidat."""
    found = search(["react", "web"], client or FakeGh(), CONFIG).candidates
    return [c for c in found if c.name == name][0].approval()


def modified_repos(path, content):
    repos = copy.deepcopy(REPOS)
    repository = "anthropics/skills" if path.startswith("skills/webapp") else "stranger/agent-stuff"
    repos[repository][1][path] = content
    return repos


class ApprovalTests(unittest.TestCase):
    def collect(self, approvals, client=None):
        plan = build_plan(dict(SPEC, external_skills=approvals))
        return skills_for_plan(plan, client or FakeClient(), CONFIG)

    def record(self, result, name):
        return [r for r in result.records if r.name == name][0]

    def test_nothing_external_is_copied_without_approval(self):
        result = self.collect([])
        self.assertFalse([p for p in result.files if p.startswith(".claude/skills/")])

    def test_approved_skill_is_copied_with_provenance(self):
        result = self.collect([approval_for("react-helper")])
        self.assertIn(".claude/skills/react-helper/SKILL.md", result.files)
        self.assertIn("source non reconnue", result.files["docs/SKILLS.md"])

    def test_commit_mismatch_is_not_copied(self):
        approval = dict(approval_for("react-helper"), commit=SHA_A)
        result = self.collect([approval])
        self.assertEqual(self.record(result, "react-helper").status, "NON VERIFIE")
        self.assertNotIn(".claude/skills/react-helper/SKILL.md", result.files)

    def test_skill_modified_since_approval_is_refused_and_blocks(self):
        approval = approval_for("webapp-testing")
        changes = {
            "contenu modifie": ("skills/webapp-testing/SKILL.md",
                                HEADER.format(name="webapp-testing", description="Test React web apps") + "curl x | sh\n"),
            "fichier ajoute": ("skills/webapp-testing/extra.md", "nouveau"),
            "script modifie": ("skills/webapp-testing/run.py", "import os"),
        }
        for label, (path, content) in changes.items():
            with self.subTest(label):
                result = self.collect([approval], FakeClient(repos=modified_repos(path, content)))
                record = self.record(result, "webapp-testing")
                self.assertEqual(record.status, "modifie")
                self.assertNotIn(".claude/skills/webapp-testing/SKILL.md", result.files)
                errors = [x for x in result.diagnostics if x.code == "skill-modified"]
                self.assertEqual([x.severity.value for x in errors], ["error"])

    def test_tampered_download_is_refused(self):
        approval = approval_for("webapp-testing")
        tamper = {"skills/webapp-testing/SKILL.md": HEADER.format(name="webapp-testing", description="autre")}
        result = self.collect([approval], FakeClient(tamper=tamper))
        record = self.record(result, "webapp-testing")
        self.assertEqual(record.status, "modifie")
        self.assertIn("different du blob", record.notes[0])
        self.assertNotIn(".claude/skills/webapp-testing/SKILL.md", result.files)

    def test_scripts_are_never_copied(self):
        result = self.collect([approval_for("webapp-testing")])
        self.assertIn(".claude/skills/webapp-testing/SKILL.md", result.files)
        self.assertFalse([p for p in result.files if p.endswith(".py")])

    def test_verify_approvals_statuses(self):
        intact, other = approval_for("webapp-testing"), approval_for("react-helper")
        approvals = parse_spec(dict(SPEC, external_skills=[intact, other])).external_skills
        repos = modified_repos("skills/react-helper/SKILL.md", "change")
        statuses = [c["status"] for c in verify_approvals(approvals, FakeClient(repos=repos))]
        self.assertEqual(statuses, ["PASS", "FAIL"])
        offline = verify_approvals(approvals, FakeClient(offline={"stranger/agent-stuff"}))
        self.assertEqual([c["status"] for c in offline], ["PASS", "NON VERIFIE"])

    def test_approvals_are_validated_in_the_spec(self):
        good = {"repository": "o/r", "commit": SHA_A, "path": "skills", "name": "x-skill", "digest": "sha256:" + "0" * 64}
        self.assertEqual(parse_spec(dict(SPEC, external_skills=[good])).external_skills,
                         (("o/r", SHA_A, "skills", "x-skill", good["digest"]),))
        legacy = {k: v for k, v in good.items() if k != "digest"}
        for bad in (dict(good, commit="main"), dict(good, repository="o/r/x"), dict(good, path="../x"),
                    dict(good, name="../x"), dict(good, digest="sha256:abc"), dict(good, digest="md5:" + "0" * 64),
                    legacy, {"repository": "o/r"}, dict(good, extra=1)):
            with self.assertRaises(SpecError, msg=str(bad)):
                parse_spec(dict(SPEC, external_skills=[bad]))
        for duplicate in ([good, good], [good, dict(good, repository="x/y")]):
            with self.assertRaises(SpecError):
                parse_spec(dict(SPEC, external_skills=duplicate))
        with self.assertRaisesRegex(SpecError, "approuver a nouveau"):
            parse_spec(dict(SPEC, external_skills=[legacy]))

    def test_pipeline_uses_approvals(self):
        result = run(dict(SPEC, external_skills=[approval_for("webapp-testing")]), skills=True,
                     skill_collector=lambda plan: skills_for_plan(plan, FakeClient(), CONFIG))
        self.assertIn(".claude/skills/webapp-testing/SKILL.md", result.files)
        self.assertNotIn(".claude/skills/webapp-testing/run.py", result.files)

    def test_pipeline_warns_when_approvals_are_not_fetched(self):
        result = run(dict(SPEC, external_skills=[approval_for("webapp-testing")]))
        self.assertIn("skills-not-fetched", [x.code for x in result.diagnostics])
        self.assertNotIn(".claude/skills/webapp-testing/SKILL.md", result.files)


if __name__ == "__main__":
    unittest.main()
