"""Configurations MCP des agents et contexte de docs/MCP.md.

Formats documentes par les editeurs (verifies le 2026-11-15) :
- `.mcp.json` a la racine, objet `mcpServers` : Claude Code (portee projet) et
  GitHub Copilot dans VS Code (destination native partagee) ; les references
  `${VAR}` sont developpees dans les en-tetes HTTP.
- `.codex/config.toml`, tables `[mcp_servers.<id>]` : Codex (projets approuves
  uniquement) ; `bearer_token_env_var` designe la variable du jeton.
Aucun secret n'est ecrit : seuls des noms de variables d'environnement.
Les valeurs proviennent du catalogue valide (forge.mcp.catalog).
"""
import json

from forge.mcp.catalog import selected_servers

SHARED_AGENTS = ("claude", "copilot")
UNVERIFIED = "NON VERIFIE"


def _shared_entry(server):
    transport = server.transport
    if transport["type"] == "http":
        headers = {"Authorization": "Bearer ${%s}" % transport["token_env"], **transport.get("headers", {})}
        return {"type": "http", "url": transport["url"], "headers": headers}
    return {"type": "stdio", "command": transport["command"], "args": list(transport["args"])}


def shared_config(servers):
    """Contenu de .mcp.json (Claude Code, Copilot)."""
    document = {"mcpServers": {s.id: _shared_entry(s) for s in servers}}
    return json.dumps(document, indent=2, ensure_ascii=True)


def _toml(value):
    # Les valeurs du catalogue sont ASCII et validees : une chaine JSON est une chaine TOML valide.
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join("%s = %s" % (_toml(k), _toml(v)) for k, v in value.items()) + " }"
    return json.dumps(value, ensure_ascii=True)


def codex_config(servers):
    """Contenu de .codex/config.toml (Codex)."""
    blocks = []
    for server in servers:
        transport = server.transport
        lines = ["[mcp_servers.%s]" % server.id]
        if transport["type"] == "http":
            lines += ["url = %s" % _toml(transport["url"]),
                      "bearer_token_env_var = %s" % _toml(transport["token_env"])]
            if transport.get("headers"):
                lines.append("http_headers = %s" % _toml(transport["headers"]))
        else:
            lines += ["command = %s" % _toml(transport["command"]), "args = %s" % _toml(transport["args"])]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _status(server, verification):
    if verification is None:
        return UNVERIFIED
    statuses = [c.status.value for c in verification.checks if c.kind in ("mcp", "package")
                and c.subject in (server.registry_name, "npm:%s" % (server.package or {}).get("name"))]
    if not statuses:
        return UNVERIFIED
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS" if all(s == "PASS" for s in statuses) else UNVERIFIED


def mcp_context(plan, verification=None):
    servers = selected_servers(plan.spec)
    agents = plan.spec.agents
    return {
        "servers": [
            {
                "id": s.id, "name": s.name, "need": s.need, "reason": s.reason, "registry_name": s.registry_name,
                "repository": s.repository, "license": s.license, "docs": s.docs, "permissions": list(s.permissions),
                "transport": "HTTP distant (%s)" % s.transport["url"] if s.transport["type"] == "http"
                else "local stdio (%s)" % " ".join([s.transport["command"], *s.transport["args"]]),
                "token_env": s.token_env, "has_token": bool(s.token_env),
                "status": _status(s, verification),
            }
            for s in servers
        ],
        "tokens": sorted({s.token_env for s in servers if s.token_env}),
        "shared_json": shared_config(servers),
        "codex_toml": codex_config(servers),
        "has_shared": any(a in agents for a in SHARED_AGENTS),
        "has_claude": "claude" in agents,
        "has_copilot": "copilot" in agents,
        "has_codex": "codex" in agents,
    }
