"""The MCP endpoint: Streamable HTTP, stateless, at /api/mcp.

Lets an AI agent (Claude Code, Claude Desktop, Cursor, ...) configure the proxy, authenticating
with the same `Authorization: Bearer gwp_...` API key the REST API takes, so scopes, expiry and
revocation behave exactly as everywhere else:

    claude mcp add --transport http ghostwire-proxy https://proxy.example.com/api/mcp \\
      --header "Authorization: Bearer gwp_..."

It lives in the API (not a Next.js route as in Ghostwire Load) because that is where the data,
the scope checks and the validate-then-reload logic are; the admin UI already forwards /api/* here,
so the URL is the same one the UI is served on. Stateless: no session is issued, so nothing is
kept between requests.
"""
import json
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.utils import get_client_ip
from app.core.version import APP_VERSION
from app.mcp.protocol import RPC, SUPPORTED_PROTOCOL_VERSIONS, ServerInfo, handle_message, rpc_error
from app.mcp.tools import ProxyApi, build_tools
from app.services import api_key_service

logger = logging.getLogger("ghostwire.mcp")

router = APIRouter()

SERVER_INFO = ServerInfo(
    name="ghostwire-proxy",
    title="Ghostwire Proxy",
    version=APP_VERSION or "1.0.0",
    instructions=(
        "Reverse proxy management (OpenResty). Look before you change: ghostwire_proxy_list_proxy_hosts and "
        "ghostwire_proxy_get_proxy_host first. Every change is checked with nginx -t before it is saved, and "
        "nothing is kept if it fails. Pass dry_run: true to see the config and diff a change would produce "
        "without saving it, and show the user that diff before applying changes to live hosts. Hosts are "
        "named by ID or by any of their domain names. Deleting hosts, certificates or users is not possible here."
    ),
)


def _json(body, status_code: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status_code, headers={"Cache-Control": "no-store"})


def _origin_allowed(request: Request) -> bool:
    """The transport requires checking Origin so a web page can't drive the endpoint.

    Editors' MCP clients send none and are let through on the key alone.
    """
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        host = urlparse(origin).netloc
    except ValueError:
        return False
    allowed = {urlparse(o).netloc for o in settings.cors_origins_list if o}
    allowed.add(request.headers.get("x-forwarded-host") or request.headers.get("host") or "")
    return bool(host) and host in allowed


@router.post("")
async def mcp_post(request: Request, db: AsyncSession = Depends(get_db)):
    if not _origin_allowed(request):
        return _json({"error": "Origin not allowed."}, 403)

    # Absent means an older client; the spec says assume 2025-03-26 rather than reject.
    version = request.headers.get("mcp-protocol-version")
    if version and version not in SUPPORTED_PROTOCOL_VERSIONS:
        return _json({"error": f'Unsupported MCP-Protocol-Version "{version}".',
                      "supported": list(SUPPORTED_PROTOCOL_VERSIONS)}, 400)

    try:
        message = json.loads(await request.body() or b"null")
    except ValueError:
        return _json(rpc_error(None, RPC.PARSE_ERROR, "Request body is not valid JSON."), 400)

    if isinstance(message, list):
        # Batching was removed in 2025-06-18 and this server never supported it.
        return _json(rpc_error(None, RPC.INVALID_REQUEST, "Send one JSON-RPC message per request."), 400)
    if not isinstance(message, dict):
        return _json(rpc_error(None, RPC.INVALID_REQUEST, "Not a JSON-RPC 2.0 request."), 400)

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not api_key_service.looks_like_key(token):
        return _json(rpc_error(
            message.get("id"), RPC.INVALID_REQUEST,
            "Send an API key: Authorization: Bearer gwp_... Create one under Settings > API keys.",
        ), 401)

    client_ip = get_client_ip(request)
    try:
        principal = await api_key_service.authenticate(db, token, client_ip)
    except api_key_service.ApiKeyError as e:
        return _json(rpc_error(message.get("id"), RPC.INVALID_REQUEST, e.detail), e.status_code)
    # Persist last-used now; tool calls run in their own sessions.
    await db.commit()

    from app.main import app  # the same app, called in-process by the tools

    api = ProxyApi(app, f"Bearer {token}", client_ip, request.headers.get("user-agent"))
    try:
        tools = build_tools(principal, api)
        response = await handle_message(message, tools=tools, info=SERVER_INFO)
    finally:
        await api.aclose()

    if response is None:
        # Notifications and responses are acknowledged with an empty 202.
        return Response(status_code=202)

    if message.get("method") == "tools/call":
        params = message.get("params") or {}
        logger.info(
            "mcp.tool tool=%s key=%s user=%s error=%s",
            params.get("name") if isinstance(params, dict) else None,
            principal.prefix, principal.user.email,
            bool((response.get("result") or {}).get("isError")) or "error" in response,
        )

    return _json(response)


@router.get("")
async def mcp_get():
    """No server-initiated messages, so no SSE stream; the spec allows declining with 405."""
    return _json({"error": "This MCP endpoint does not stream. POST JSON-RPC messages instead."}, 405)


@router.delete("")
async def mcp_delete():
    """Sessions are never issued, so there is none to end."""
    return _json({"error": "This MCP endpoint is stateless; there is no session to end."}, 405)
