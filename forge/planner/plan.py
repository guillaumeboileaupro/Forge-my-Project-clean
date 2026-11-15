"""Planificateur : compatibilites + regles -> plan de generation (sans IA)."""
from dataclasses import dataclass

from forge import diagnostics as d
from forge.config.catalog import load_catalog
from forge.config.spec import ProjectSpec, parse_spec
from forge.mcp.catalog import mcp_diagnostics
from forge.rules.compatibility import resolve
from forge.rules.engine import compose, load_rules
from forge.security.controls import security_diagnostics


@dataclass(frozen=True)
class Plan:
    spec: ProjectSpec
    resolution: object  # forge.rules.compatibility.Resolution
    composition: object  # forge.rules.engine.Composition
    architecture: dict  # {"source": "manual"|"suggested"|"undefined", "manual": str, "suggested": list}
    diagnostics: tuple

    @property
    def ok(self):
        return not d.has_errors(self.diagnostics)

    @property
    def files(self):
        return dict(sorted(self.composition.files.items()))


def plan_probe(spec, resolution):
    """Vue minimale (spec + resolution) pour les controles qui ne dependent pas des fichiers."""
    return Plan(spec, resolution, None, {}, ())


def _architecture(spec, composition, out):
    suggested = list(composition.sections["architecture"])
    if spec.architecture:
        source = "manual"
    elif suggested:
        source = "suggested"
        out.append(d.info("architecture-suggested", "Architecture suggeree par les regles locales : a valider ou modifier"))
    else:
        source = "undefined"
        out.append(d.warning("architecture-undefined", "Aucune architecture fournie ni suggeree : preciser l'architecture"))
    return {"source": source, "manual": spec.architecture, "suggested": suggested}


def build_plan(data, catalog=None, rules=None):
    """Construit le plan a partir d'un dict JSON ou d'un ProjectSpec deja valide."""
    spec = data if isinstance(data, ProjectSpec) else parse_spec(data)
    catalog = catalog or load_catalog()
    rules = rules if rules is not None else load_rules(catalog)
    resolution = resolve(spec, catalog)
    composition = compose(rules, spec, resolution.ids())
    out = list(resolution.diagnostics) + list(composition.diagnostics)
    out.extend(security_diagnostics(plan_probe(spec, resolution)))
    out.extend(mcp_diagnostics(spec, resolution.ids()))
    if not spec.description:
        out.append(d.warning("description-empty", "Description vide : les documents resteront generiques"))
    architecture = _architecture(spec, composition, out)
    return Plan(spec, resolution, composition, architecture, tuple(out))
