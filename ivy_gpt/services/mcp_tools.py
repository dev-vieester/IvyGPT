import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.config import PROJECT_ROOT, settings
from ivy_gpt.db.crud import list_mcp_servers


logger = logging.getLogger(__name__)

TRANSPORT_ALIASES = {
    "stdio": "stdio",
    "streamable-http": "streamable-http",
    "streamable_http": "streamable-http",
    "httpstream": "streamable-http",
    "httpstreams": "streamable-http",
    "http-stream": "streamable-http",
    "http-streams": "streamable-http",
    "sse": "sse",
}


def get_venv_python() -> str:
    if sys.executable:
        return sys.executable

    if os.name == "nt":
        return str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

    return str(PROJECT_ROOT / ".venv" / "bin" / "python")


def expand_config_value(value: Any) -> Any:
    replacements = {
        "project_root": str(PROJECT_ROOT),
        "venv_python": get_venv_python(),
    }

    if isinstance(value, str):
        expanded = value.format(**replacements)
        return os.path.expandvars(os.path.expanduser(expanded))

    if isinstance(value, list):
        return [expand_config_value(item) for item in value]

    if isinstance(value, dict):
        return {
            key: expand_config_value(item)
            for key, item in value.items()
        }

    return value


def normalize_transport(server_name: str, server_config: dict[str, Any]) -> dict[str, Any] | None:
    transport = str(server_config.get("transport", "")).strip().lower()

    if not transport:
        if server_config.get("url"):
            transport = "streamable-http"
        elif server_config.get("command"):
            transport = "stdio"

    normalized_transport = TRANSPORT_ALIASES.get(transport)

    if not normalized_transport:
        logger.warning(
            "Skipping MCP server %s because transport %r is not supported. "
            "Use stdio, streamable-http, httpstreams, or sse.",
            server_name,
            transport,
        )
        return None

    normalized_config = dict(server_config)
    normalized_config["transport"] = normalized_transport

    if normalized_transport == "stdio" and not normalized_config.get("command"):
        logger.warning("Skipping MCP stdio server %s because command is missing.", server_name)
        return None

    if normalized_transport in {"streamable-http", "sse"} and not normalized_config.get("url"):
        logger.warning("Skipping MCP HTTP server %s because url is missing.", server_name)
        return None

    headers = normalized_config.get("headers")

    if headers is None:
        normalized_config.pop("headers", None)
    elif not isinstance(headers, dict):
        logger.warning("Skipping MCP server %s because headers must be an object.", server_name)
        return None
    else:
        normalized_config["headers"] = {
            str(key): str(value)
            for key, value in headers.items()
            if str(key).strip()
        }

    if normalized_transport in {"streamable-http", "sse"}:
        normalized_config.pop("command", None)
        normalized_config.pop("args", None)

    if normalized_transport == "stdio":
        normalized_config.pop("url", None)
        normalized_config.pop("headers", None)

    normalized_config = {
        key: value
        for key, value in normalized_config.items()
        if value is not None
    }

    return normalized_config


def serialize_mcp_tool(tool: Any) -> dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    input_schema: dict[str, Any] | None = None

    if args_schema is not None:
        if hasattr(args_schema, "model_json_schema"):
            input_schema = args_schema.model_json_schema()
        elif isinstance(args_schema, dict):
            input_schema = args_schema

    return {
        "name": str(getattr(tool, "name", "")),
        "description": str(getattr(tool, "description", "") or ""),
        "input_schema": input_schema or {},
    }


async def discover_mcp_server_tools(server_name: str, server_config: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_config = normalize_transport(server_name, server_config)

    if normalized_config is None:
        raise ValueError("Unsupported or incomplete MCP server configuration.")

    client = MultiServerMCPClient({
        server_name: expand_config_value(normalized_config)
    })
    tools = await client.get_tools()

    return [
        serialize_mcp_tool(tool)
        for tool in tools
    ]


def load_mcp_server_config() -> dict[str, dict[str, Any]]:
    config_path = Path(settings.mcp_config_path)

    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    if not config_path.exists():
        logger.info("MCP config file not found at %s; skipping MCP tools.", config_path)
        return {}

    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.exception("Could not read MCP config file at %s", config_path)
        return {}

    servers = raw_config.get("servers") or raw_config.get("mcpServers") or raw_config

    if not isinstance(servers, dict):
        logger.warning("MCP config at %s must contain a server map.", config_path)
        return {}

    enabled_servers: dict[str, dict[str, Any]] = {}

    for name, server_config in servers.items():
        if not isinstance(server_config, dict):
            logger.warning("Skipping MCP server %s because its config is not an object.", name)
            continue

        if server_config.get("enabled", True) is False:
            continue

        normalized_config = {
            key: value
            for key, value in server_config.items()
            if key != "enabled"
        }
        normalized_config = normalize_transport(name, normalized_config)

        if normalized_config is None:
            continue

        enabled_servers[name] = expand_config_value(normalized_config)

    return enabled_servers


async def load_user_mcp_server_config(db: AsyncSession | None, user_id: str | None) -> dict[str, dict[str, Any]]:
    if db is None or user_id is None:
        return {}

    server_rows = await list_mcp_servers(db, user_id)
    enabled_servers: dict[str, dict[str, Any]] = {}

    for server in server_rows:
        if not server.enabled:
            continue

        server_config: dict[str, Any] = {
            "transport": server.transport,
            "command": server.command,
            "args": server.args or [],
            "url": server.url,
            "headers": server.headers or {},
        }
        normalized_config = normalize_transport(server.name, server_config)

        if normalized_config is None:
            continue

        enabled_servers[server.name] = expand_config_value(normalized_config)

    return enabled_servers


async def get_mcp_tools(db: AsyncSession | None = None, user_id: str | None = None) -> list:
    servers = load_mcp_server_config()
    servers.update(await load_user_mcp_server_config(db, user_id))

    if not servers:
        return []

    try:
        client = MultiServerMCPClient(servers)
        return await client.get_tools()
    except Exception:
        logger.exception("Could not load MCP tools.")
        return []
