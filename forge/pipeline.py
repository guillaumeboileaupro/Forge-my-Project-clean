"""Point d'entree du moteur pour l'interface et la CLI.

    result = run(config_dict, verify=True, skills=True)

Etapes : validation -> plan -> [verification reseau] -> rendu -> [skills].
Les etapes reseau ne s'executent que si elles sont demandees. Aucune
ecriture disque : `result.files` est un apercu {chemin: contenu}.
"""
from dataclasses import dataclass, field

from forge import diagnostics as d
from forge.diagnostics import ForgeError
from forge.generator.render import render_plan
from forge.planner.plan import build_plan
from forge.skills.service import skills_for_plan
from forge.verification.report import verify_plan


@dataclass
class Result:
    plan: object
    files: dict = field(default_factory=dict)
    verification: object = None
    skills: object = None

    @property
    def diagnostics(self):
        found = list(self.plan.diagnostics)
        if self.verification is not None:
            found += list(self.verification.diagnostics)
        if self.skills is not None:
            found += list(self.skills.diagnostics)
        elif self.plan.spec.external_skills:
            found.append(d.warning("skills-not-fetched", "%d skill(s) externe(s) approuve(s) non copie(s) : "
                                   "activer la recuperation des skills (reseau)" % len(self.plan.spec.external_skills)))
        return found

    def as_dict(self):
        return {
            "ok": not d.has_errors(self.diagnostics),
            "rules": list(self.plan.composition.rules),
            "files": sorted(self.files),
            "diagnostics": [x.as_dict() for x in self.diagnostics],
            "verification": self.verification.as_dict()["checks"] if self.verification else None,
            "skills": [{"name": r.name, "status": r.status, "commit": r.commit, "notes": r.notes}
                       for r in self.skills.records] if self.skills else None,
        }


def _merge(files, extra):
    clashes = sorted(set(files) & set(extra))
    if clashes:
        raise ForgeError("Conflit de fichiers generes : " + ", ".join(clashes))
    files.update(extra)


def run(data, verify=False, skills=False, catalog=None, rules=None, verifier=None, skill_collector=None):
    """Execute le pipeline. `verifier` / `skill_collector` sont injectables (tests, UI)."""
    plan = build_plan(data, catalog, rules)
    result = Result(plan)
    if not plan.ok:
        raise ForgeError("Plan invalide : generation bloquee", [x for x in plan.diagnostics if x.severity is d.Severity.ERROR])
    if verify:
        result.verification = (verifier or verify_plan)(plan)
    result.files = render_plan(plan, verification=result.verification)
    if skills:
        result.skills = (skill_collector or skills_for_plan)(plan)
        _merge(result.files, result.skills.files)
    result.files = dict(sorted(result.files.items()))
    return result
