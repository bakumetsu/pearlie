"""One request to a configured address; shared by the Test button and /api/health."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from app.connections_store import ConnectionStore
from app.logs import install_http_hooks
from app.sources.auth import build_auth

logger = logging.getLogger("pearlie")


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str
    version: str | None = None


def _stash_version(resp: httpx.Response) -> str | None:
    try:
        value = resp.json()["data"]["version"]["version"]
    except (ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


def probe_connection(app: FastAPI, name: str) -> ProbeResult:
    """Probe one known connection name. Never raises for network errors."""
    store: ConnectionStore = app.state.connection_store
    address = store.address(name)
    if not address:
        return ProbeResult(False, "not configured")

    settings = app.state.settings
    transport: httpx.BaseTransport | None = getattr(app.state, "connection_transport", None)
    if settings.mode == "fixture" and transport is None:
        return ProbeResult(False, "fixture mode: no real connection")

    secret = store.effective_secret(name)
    site_auth = build_auth(name, store.field_values(name))
    if site_auth.missing:
        return ProbeResult(False, "missing: " + ", ".join(site_auth.missing))

    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = dict(site_auth.headers)
    json_body: dict[str, str] | None = None
    params: dict[str, str] | None = None

    if name == "stash":
        method = "POST"
        url = address + "/graphql"
        json_body = {"query": "{ version { version } }"}
        if secret:
            headers["ApiKey"] = secret
    elif name == "komga":
        url = address + "/api/v1/libraries"
        if secret:
            headers["X-API-Key"] = secret
    elif name == "danbooru":
        url = address + "/posts.json?limit=1"
    elif name in ("gelbooru", "rule34"):
        url = address + "/index.php"
        params = {"page": "dapi", "s": "post", "q": "index", "json": "1", "limit": "1"}
        params.update(site_auth.params)
    elif name == "nhentai":
        url = address + "/api/v2/search?query=a"

    client = install_http_hooks(
        httpx.Client(transport=transport, timeout=10.0, follow_redirects=False), name
    )
    try:
        if method == "POST":
            resp = client.post(url, json=json_body, headers=headers)
        else:
            resp = client.get(url, params=params, headers=headers, auth=site_auth.basic)
    except httpx.HTTPError as exc:
        logger.warning("connection test for %s failed: %s", name, type(exc).__name__)
        return ProbeResult(False, "unreachable")
    finally:
        client.close()

    if resp.status_code == 200:
        return ProbeResult(True, "connected", _stash_version(resp) if name == "stash" else None)
    if resp.status_code in (401, 403):
        return ProbeResult(False, "key rejected")
    return ProbeResult(False, f"HTTP {resp.status_code}")
