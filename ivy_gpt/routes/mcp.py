import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.core.agent import clear_agent_cache_for_user
from ivy_gpt.db.crud import create_mcp_server, delete_mcp_server, list_mcp_servers
from ivy_gpt.db.models import User
from ivy_gpt.db.session import get_db
from ivy_gpt.config import settings
from ivy_gpt.schemas.mcp import (
    MCPOAuthStartRequest,
    MCPOAuthStartResponse,
    MCPServerCreateRequest,
    MCPServerListResponse,
    MCPServerResponse,
)
from ivy_gpt.services.auth import create_jwt, decode_jwt, get_current_user, redis_client
from ivy_gpt.services.mcp_tools import discover_mcp_server_tools, normalize_transport


router = APIRouter(prefix="/mcp", tags=["mcp"])
OAUTH_STATE_TTL_SECONDS = 10 * 60


def mask_headers(headers: dict[str, str] | None) -> dict[str, str]:
    return {
        str(key): "******"
        for key in (headers or {})
    }


def mcp_server_response(server) -> MCPServerResponse:
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport=server.transport,
        command=server.command,
        args=server.args or [],
        url=server.url,
        headers=mask_headers(server.headers),
        tool_specs=server.tool_specs or [],
        enabled=server.enabled,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def oauth_state_key(state: str) -> str:
    return f"mcp:oauth:state:{state}"


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


async def fetch_oauth_metadata(mcp_url: str) -> dict:
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get(mcp_url)

        if response.status_code != 401:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MCP server did not request OAuth authorization."
            )

        authenticate = response.headers.get("www-authenticate", "")
        metadata_url = ""

        for part in authenticate.split(","):
            key, _, value = part.strip().partition("=")
            if key.lower() == "resource_metadata":
                metadata_url = value.strip().strip('"')
                break

        if not metadata_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MCP server did not provide OAuth protected-resource metadata."
            )

        protected_resource_response = await client.get(metadata_url)
        protected_resource_response.raise_for_status()
        protected_resource = protected_resource_response.json()
        authorization_servers = protected_resource.get("authorization_servers") or []

        if not authorization_servers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth protected-resource metadata did not include an authorization server."
            )

        authorization_server = str(authorization_servers[0]).rstrip("/")
        auth_server_response = await client.get(f"{authorization_server}/.well-known/oauth-authorization-server")
        auth_server_response.raise_for_status()
        auth_server = auth_server_response.json()

        return {
            "resource": protected_resource.get("resource") or mcp_url,
            "authorization_endpoint": auth_server["authorization_endpoint"],
            "token_endpoint": auth_server["token_endpoint"],
            "registration_endpoint": auth_server.get("registration_endpoint"),
            "scopes_supported": auth_server.get("scopes_supported") or [],
        }


async def register_oauth_client(registration_endpoint: str | None, redirect_uri: str) -> str:
    if not registration_endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth server does not support dynamic client registration."
        )

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            registration_endpoint,
            json={
                "client_name": "IvyGPT",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth client registration failed."
        )

    client_id = response.json().get("client_id")

    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth client registration did not return a client_id."
        )

    return str(client_id)


@router.get("/servers", response_model=MCPServerListResponse)
async def get_user_mcp_servers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> MCPServerListResponse:
    servers = await list_mcp_servers(db, current_user.id)
    return MCPServerListResponse(
        servers=[
            mcp_server_response(server)
            for server in servers
        ]
    )


@router.post("/oauth/start", response_model=MCPOAuthStartResponse)
async def start_mcp_oauth(
    payload: MCPOAuthStartRequest,
    current_user: User = Depends(get_current_user)
) -> MCPOAuthStartResponse:
    metadata = await fetch_oauth_metadata(payload.url)
    redirect_uri = f"{settings.app_base_url.rstrip('/')}/mcp/oauth/callback"
    client_id = await register_oauth_client(metadata.get("registration_endpoint"), redirect_uri)
    code_verifier = secrets.token_urlsafe(64)
    state = create_jwt(
        subject=current_user.id,
        token_type="mcp_oauth_state",
        expires_delta=timedelta(minutes=10)
    )
    scopes = [
        scope
        for scope in ("openid", "profile", "email", "offline_access")
        if scope in metadata["scopes_supported"]
    ]

    await redis_client.setex(
        oauth_state_key(state),
        OAUTH_STATE_TTL_SECONDS,
        json.dumps({
            "user_id": current_user.id,
            "name": payload.name,
            "url": payload.url,
            "headers": payload.headers,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "token_endpoint": metadata["token_endpoint"],
            "resource": metadata["resource"],
        })
    )

    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
        "resource": metadata["resource"],
    }

    if scopes:
        query["scope"] = " ".join(scopes)

    return MCPOAuthStartResponse(
        authorization_url=f"{metadata['authorization_endpoint']}?{urlencode(query)}",
        state=state
    )


@router.get("/oauth/callback")
async def mcp_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing MCP OAuth callback parameters."
        )

    payload = decode_jwt(state, "mcp_oauth_state")
    state_data_raw = await redis_client.get(oauth_state_key(state))

    if not state_data_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP OAuth state expired or was already used."
        )

    await redis_client.delete(oauth_state_key(state))
    state_data = json.loads(state_data_raw)

    if state_data["user_id"] != payload["sub"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP OAuth state does not match the user."
        )

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            state_data["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": state_data["client_id"],
                "redirect_uri": state_data["redirect_uri"],
                "code_verifier": state_data["code_verifier"],
                "resource": state_data["resource"],
            }
        )

    if token_response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP OAuth token exchange failed."
        )

    token_payload = token_response.json()
    access_token = token_payload.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP OAuth server did not return an access token."
        )

    headers = {
        **(state_data.get("headers") or {}),
        "Authorization": f"Bearer {access_token}",
    }
    normalized_config = normalize_transport(
        state_data["name"],
        {
            "transport": "streamable-http",
            "url": state_data["url"],
            "headers": headers,
        }
    )

    if normalized_config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth MCP server configuration is incomplete."
        )

    tool_specs = await discover_mcp_server_tools(state_data["name"], normalized_config)
    expires_at = None

    if token_payload.get("expires_in"):
        expires_at = int(datetime.utcnow().timestamp()) + int(token_payload["expires_in"])

    try:
        await create_mcp_server(
            db=db,
            user_id=state_data["user_id"],
            name=state_data["name"],
            transport=normalized_config["transport"],
            url=normalized_config.get("url"),
            headers=normalized_config.get("headers") or {},
            tool_specs=tool_specs,
            oauth_tokens={
                "access_token": access_token,
                "refresh_token": token_payload.get("refresh_token"),
                "token_type": token_payload.get("token_type"),
                "expires_at": expires_at,
                "scope": token_payload.get("scope"),
            },
            enabled=True,
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An MCP server with this name already exists for your account."
        ) from exc

    await clear_agent_cache_for_user(state_data["user_id"])
    return RedirectResponse(f"{settings.app_base_url.rstrip('/')}/?mcp_connected=1")


@router.post("/servers", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED)
async def add_user_mcp_server(
    payload: MCPServerCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> MCPServerResponse:
    normalized_config = normalize_transport(
        payload.name,
        {
            "transport": payload.transport,
            "command": payload.command,
            "args": payload.args,
            "url": payload.url,
            "headers": payload.headers,
        }
    )

    if normalized_config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported or incomplete MCP server configuration."
        )

    try:
        tool_specs = await discover_mcp_server_tools(payload.name, normalized_config)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not connect to MCP server or discover tools: {exc}"
        ) from exc

    try:
        server = await create_mcp_server(
            db=db,
            user_id=current_user.id,
            name=payload.name,
            transport=normalized_config["transport"],
            command=normalized_config.get("command"),
            args=normalized_config.get("args") or [],
            url=normalized_config.get("url"),
            headers=normalized_config.get("headers") or {},
            tool_specs=tool_specs,
            enabled=payload.enabled
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An MCP server with this name already exists for your account."
        ) from exc

    await clear_agent_cache_for_user(current_user.id)
    return mcp_server_response(server)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_mcp_server(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> None:
    deleted = await delete_mcp_server(db, current_user.id, server_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP server was not found."
        )

    await clear_agent_cache_for_user(current_user.id)
