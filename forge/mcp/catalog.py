"""Catalogue des serveurs MCP proposes (catalogs/mcp/servers.json) et pertinence.

Le catalogue est une donnee versionnee, validee avant usage : aucun serveur
hors catalogue n'est accepte, aucune valeur n'est executee par Forge-my-Project.
Un serveur n'est propose que s'il est pertinent pour la configuration.
"""
import json
import re
from dataclasses import dataclass
from functools import lru_cache

from forge import CATALOGS_DIR
from forge import diagnostics as d

SERVER_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
REGISTRY_NAME = re.compile(r"^[a-z0-9.-]+/[A-Za-z0-9._-]+$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
HEADER = re.compile(r"^[A-Za-z0-9-]{1,64}$")
SAFE_VALUE = re.compile(r"^[A-Za-z0-9@._/:,=+-]{1,200}$")
HTTPS = re.compile(r"^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/-]*)?$")
PROJECT_TYPES = ("library", "cli", "api", "web")
MAX_SERVERS = 10


class McpCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class McpServer:
    id: str
    name: str
    need: str
    reason: str
    project_types: tuple  # vide : pertinent pour tout projet
    registry_name: str
    repository: str
    license: str
    docs: str
    transport: dict
    permissions: tuple
    package: dict = None
    runtime: str = ""

    @property
    def token_env(self):
        return self.transport.get("token_env", "")

    def relevant(self, project_type):
        return not self.project_types or project_type in self.project_types


def _require(condition, message):
    if not condition:
        raise McpCatalogError("catalogs/mcp/servers.json : " + message)


def _text(raw, key, where):
    value = raw.get(key)
    _require(isinstance(value, str) and value.strip() and len(value) <= 300, "%s : %s invalide" % (where, key))
    return value


def _transport(raw, where):
    _require(isinstance(raw, dict), where + " : transport invalide")
    kind = raw.get("type")
    if kind == "http":
        _require(set(raw) <= {"type", "url", "headers", "token_env"}, where + " : champ de transport inconnu")
        _require(HTTPS.fullmatch(raw.get("url", "")) is not None, where + " : URL HTTPS requise")
        headers = raw.get("headers", {})
        _require(isinstance(headers, dict) and all(HEADER.fullmatch(k) and isinstance(v, str) and SAFE_VALUE.fullmatch(v)
                                                    for k, v in headers.items()), where + " : en-tetes invalides")
        _require("Authorization" not in headers, where + " : aucun secret dans le catalogue (token_env)")
        _require(ENV_NAME.fullmatch(raw.get("token_env", "")) is not None, where + " : token_env invalide")
    elif kind == "stdio":
        _require(set(raw) <= {"type", "command", "args"}, where + " : champ de transport inconnu")
        _require(raw.get("command") in ("npx", "uvx"), where + " : commande non autorisee")
        args = raw.get("args")
        _require(isinstance(args, list) and args and all(isinstance(a, str) and SAFE_VALUE.fullmatch(a) for a in args),
                 where + " : arguments invalides")
    else:
        raise McpCatalogError("catalogs/mcp/servers.json : %s : transport http ou stdio attendu" % where)
    return dict(raw)


def _package(raw, transport, where):
    if raw is None:
        return None
    _require(isinstance(raw, dict) and raw.get("ecosystem") == "npm", where + " : package npm attendu")
    name, version = raw.get("name", ""), raw.get("version", "")
    _require(re.fullmatch(r"(@[a-z0-9-]+/)?[a-z0-9.-]+", name) and re.fullmatch(r"\d+\.\d+\.\d+", version),
             where + " : package ou version invalide")
    _require("%s@%s" % (name, version) in transport.get("args", []), where + " : version executee differente du package epingle")
    return dict(raw)


def parse_server(raw):
    _require(isinstance(raw, dict), "serveur invalide")
    server_id = raw.get("id", "")
    _require(SERVER_ID.fullmatch(server_id) is not None, "identifiant invalide")
    where = "serveur " + server_id
    relevance = raw.get("relevance") or {}
    types = tuple(relevance.get("project_types", ()))
    _require(set(types) <= set(PROJECT_TYPES), where + " : type de projet inconnu")
    _require(REGISTRY_NAME.fullmatch(raw.get("registry_name", "")) is not None, where + " : nom de registre invalide")
    _require(re.fullmatch(r"https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+", raw.get("repository", "")) is not None,
             where + " : depot GitHub attendu")
    _require(HTTPS.fullmatch(raw.get("docs", "")) is not None, where + " : documentation HTTPS requise")
    permissions = raw.get("permissions")
    _require(isinstance(permissions, list) and permissions and all(isinstance(p, str) for p in permissions),
             where + " : permissions a documenter")
    transport = _transport(raw.get("transport"), where)
    package = _package(raw.get("package"), transport, where)
    _require(transport["type"] == "http" or package is not None, where + " : un serveur local exige un package epingle")
    return McpServer(
        id=server_id, name=_text(raw, "name", where), need=_text(raw, "need", where),
        reason=_text(relevance, "reason", where), project_types=types, registry_name=raw["registry_name"],
        repository=raw["repository"], license=_text(raw, "license", where), docs=raw["docs"], transport=transport,
        permissions=tuple(permissions), package=package, runtime=raw.get("runtime", ""),
    )


@lru_cache(maxsize=4)
def load_mcp_catalog(path=None):
    """Retourne {id: McpServer} ; toute anomalie du catalogue est une erreur."""
    data = json.loads((path or CATALOGS_DIR / "mcp" / "servers.json").read_text(encoding="utf-8"))
    _require(data.get("schema_version") == 1 and isinstance(data.get("servers"), list), "schema invalide")
    servers = [parse_server(raw) for raw in data["servers"]]
    _require(len({s.id for s in servers}) == len(servers), "identifiant duplique")
    return {s.id: s for s in servers}


def selected_servers(spec, catalog=None):
    catalog = catalog if catalog is not None else load_mcp_catalog()
    return [catalog[i] for i in spec.mcp_servers if i in catalog]


def mcp_diagnostics(spec, technology_ids, catalog=None):
    """Serveur inconnu ou non pertinent = erreur ; prerequis du poste = avertissement."""
    catalog = catalog if catalog is not None else load_mcp_catalog()
    out = []
    for server_id in spec.mcp_servers:
        server = catalog.get(server_id)
        if server is None:
            out.append(d.error("mcp-unknown", "Serveur MCP inconnu du catalogue : %s" % server_id, server_id))
        elif not server.relevant(spec.project_type):
            out.append(d.error("mcp-not-relevant", "Serveur MCP %s non pertinent pour un projet %s"
                               % (server.name, spec.project_type), server_id))
        elif server.runtime == "node" and "node" not in technology_ids:
            out.append(d.warning("mcp-runtime", "%s s'execute avec npx : Node.js requis sur le poste de developpement"
                                 % server.name, server_id))
    return out
