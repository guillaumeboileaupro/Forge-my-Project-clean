"""Verification d'un plan : packages, versions, vulnerabilites, runtimes, API (T11).

Appel explicite uniquement : c'est la seule etape du moteur qui interroge
les registres. Erreur critique (package inexistant, version absente,
vulnerabilite haute/critique, runtime en fin de vie) = blocage.
"""
import datetime
from dataclasses import dataclass

from forge import diagnostics as d
from forge.diagnostics import Status
from forge.mcp.catalog import selected_servers
from forge.verification import checks, npm_peers
from forge.generator.stack import load_ci_catalog
from forge.security.controls import load_security_tools
from forge.verification.http import fetch_json


@dataclass(frozen=True)
class VerificationReport:
    checks: tuple
    diagnostics: tuple

    @property
    def ok(self):
        return not d.has_errors(self.diagnostics)

    def find(self, kind, subject_prefix):
        return [c for c in self.checks if c.kind == kind and c.subject.startswith(subject_prefix)]

    def package_status(self, ecosystem, package):
        """Etat agrege d'une dependance (registre + vulnerabilites) et details."""
        prefix = "%s:%s" % (ecosystem, package)
        found = [c for c in self.checks if c.kind in ("package", "vulnerabilities")
                 and (c.subject == prefix or c.subject.startswith(prefix + "@"))]
        if not found:
            return Status.NON_VERIFIE, {}
        details = next((c.details for c in found if c.kind == "package"), {})
        if any(c.status is Status.FAIL for c in found):
            return Status.FAIL, details
        if len(found) < 2 or any(c.status is Status.NON_VERIFIE for c in found):
            return Status.NON_VERIFIE, details
        return Status.PASS, details

    def as_dict(self):
        return {"ok": self.ok, "checks": [c.as_dict() for c in self.checks],
                "diagnostics": [x.as_dict() for x in self.diagnostics]}


def _diagnostic(check):
    if check.status is Status.FAIL:
        return d.error("verification-" + check.kind, "%s : %s" % (check.subject, check.message), check.subject)
    if check.status is Status.NON_VERIFIE and check.kind != "api":
        return d.warning("unverified-" + check.kind, "%s : %s" % (check.subject, check.message), check.subject)
    return None


def _verify_package(ecosystem, package, wanted, fetch):
    result = [checks.check_package(ecosystem, package, wanted, fetch)]
    version = result[0].details.get("version")
    if result[0].status is Status.PASS and version:
        result.append(checks.check_vulnerabilities(ecosystem, package, version, fetch))
    else:
        result.append(checks.Check("vulnerabilities", "%s:%s" % (ecosystem, package), Status.NON_VERIFIE,
                                   "Audit impossible sans version verifiee"))
    return result


def active_companions(plan, tech):
    """Packages installes avec une technologie (ex. configuration ESLint)."""
    ids = plan.resolution.ids()
    return [package for package, when in tech.companions if not when or ids.intersection(when)]


def _cached(fetch):
    """Memorise les lectures (GET) pour ne pas interroger deux fois le meme registre."""
    memory = {}

    def cached(url, payload=None):
        if payload is not None:
            return fetch(url, payload)
        if url not in memory:
            memory[url] = fetch(url)
        return memory[url]

    return cached


def _resolve_npm(plan, fetch):
    requested = []
    for tech in plan.resolution.technologies:
        if tech.ecosystem == "npm":
            requested.append((tech.package, plan.spec.versions.get(tech.id)))
            requested.extend((package, None) for package in active_companions(plan, tech))
    if not requested:
        return {}, None
    return npm_peers.resolve(requested, fetch)


def _verify_security_tools(plan, fetch):
    """Outils du job security : versions PyPI epinglees (+ OSV) et binaire Gitleaks."""
    try:
        tools = load_security_tools()
    except (OSError, ValueError) as exc:
        return [checks.Check("tool", "catalogs/security/tools.json", Status.FAIL, "Catalogue invalide : %s" % exc)]
    gitleaks = tools["gitleaks"]
    results = [checks.check_release_asset(gitleaks["repository"], gitleaks["version"], gitleaks["asset"], gitleaks["sha256"], fetch)]
    if "python" in plan.resolution.ids():
        for name, version in sorted(tools["pypi"].items()):
            results.extend(_verify_package("pypi", name, version, fetch))
    return results


def _verify_actions(fetch):
    try:
        actions = load_ci_catalog()["actions"].values()
    except (OSError, ValueError) as exc:
        return [checks.Check("action", "catalogs/ci/actions.json", Status.FAIL, "Catalogue CI invalide : %s" % exc)]
    return [checks.check_action(a["repository"], a["tag"], a["sha"], fetch) for a in actions]


def verify_plan(plan, fetch=fetch_json, today=None):
    """Verifie chaque technologie du plan. `today` (AAAA-MM-JJ) est injectable pour les tests."""
    today = today or datetime.date.today().isoformat()
    fetch = _cached(fetch)
    results = []
    npm_versions, compatibility = _resolve_npm(plan, fetch)
    for tech in plan.resolution.technologies:
        if tech.package:
            wanted = npm_versions.get(tech.package, plan.spec.versions.get(tech.id))
            results.extend(_verify_package(tech.ecosystem, tech.package, wanted, fetch))
            results.append(checks.api_unverified(tech))
            for package in active_companions(plan, tech):
                results.extend(_verify_package(tech.ecosystem, package, npm_versions.get(package), fetch))
        if tech.eol_product and tech.id in plan.resolution.versions:
            results.append(checks.check_runtime(tech.eol_product, plan.resolution.versions[tech.id], today, fetch))
    if compatibility is not None:
        results.append(compatibility)
    for server in selected_servers(plan.spec):
        results.append(checks.check_mcp_server(server, fetch))
        if server.package:
            results.extend(_verify_package("npm", server.package["name"], server.package["version"], fetch))
    if ".github/workflows/ci.yml" in plan.files:
        results.extend(_verify_actions(fetch))
        results.extend(_verify_security_tools(plan, fetch))
    diagnostics = tuple(x for x in map(_diagnostic, results) if x is not None)
    return VerificationReport(tuple(results), diagnostics)
