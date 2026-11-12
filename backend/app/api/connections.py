"""Connections router: manage per-connection addresses and secrets."""

from __future__ import annotations

import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, SecretStr, StrictBool

from app.api.errors import ApiError
from app.api.guard import write_guard
from app.connections_store import (
    FIELDS,
    FIXED_HOSTS,
    NAMES,
    PRIMARY,
    ConnectionStore,
    StoreError,
)
from app.sources.auth import build_auth

logger = logging.getLogger("pearlie")

router = APIRouter(prefix="/api/connections")


class FieldOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    state: Literal["set", "missing"]
    locked: bool
    primary: bool


class ConnectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    address: str
    key: Literal["set", "missing"]
    address_fixed: bool
    address_locked: bool
    key_locked: bool
    fields: list[FieldOut]
    restart_needed: bool = False


class ConnectionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_store: bool
    connections: list[ConnectionOut]


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str | None = None
    secret: SecretStr | None = None
    clear_secret: StrictBool = False
    fields: dict[str, SecretStr] | None = None
    clear_fields: list[str] = []


class TestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str


def _build_out(name: str, store: ConnectionStore) -> ConnectionOut:
    locked = store.env_locked(name)
    return ConnectionOut(
        name=name,
        address=store.address(name),
        key=store.secret_state(name),
        address_fixed=name in FIXED_HOSTS,
        address_locked=locked["address"],
        key_locked=locked["secret"],
        fields=[
            FieldOut(
                id=f.id,
                label=f.label,
                state=store.field_state(name, f.id),
                locked=store.field_locked(name, f.id),
                primary=PRIMARY[name] == f.id,
            )
            for f in FIELDS[name]
        ],
    )


@router.get("", response_model=ConnectionsOut)
def get_connections(request: Request) -> ConnectionsOut:
    store: ConnectionStore = request.app.state.connection_store
    connections = [_build_out(name, store) for name in NAMES]
    return ConnectionsOut(can_store=store.can_store(), connections=connections)


@router.put("/{name}", response_model=ConnectionOut, dependencies=[Depends(write_guard)])
def put_connection(request: Request, name: str, body: ConnectionIn) -> ConnectionOut:
    store: ConnectionStore = request.app.state.connection_store
    if name not in NAMES:
        raise ApiError(404, "not_found", "unknown connection")
    secret_value: str | None = body.secret.get_secret_value() if body.secret else None
    try:
        field_values: dict[str, str] = {
            k: v.get_secret_value() for k, v in (body.fields or {}).items()
        }
        store.save(
            name,
            body.address,
            secret_value,
            body.clear_secret,
            fields=field_values,
            clear_fields=body.clear_fields,
        )
    except StoreError as exc:
        code = exc.code
        if code == "no_master_key":
            raise ApiError(
                409, "no_master_key", "Set PEARLIE_SECRET_KEY in .env to save keys here"
            ) from exc
        if code == "locked":
            raise ApiError(409, "locked", "set in .env") from exc
        if code == "bad_address":
            raise ApiError(422, "invalid", "invalid address", field="address") from exc
        if code in ("unknown_field", "bad_value"):
            raise ApiError(422, "invalid", "invalid field", field="fields") from exc
        if code == "unknown":
            raise ApiError(404, "not_found", "unknown connection") from exc
        raise ApiError(500, "error", "unexpected store error") from exc
    out = _build_out(name, store)
    if name in ("stash", "komga"):
        from app.main import rebuild_client

        rebuild_client(request.app, name)
        if name == "stash":
            out.restart_needed = bool(
                {"library_stash", "media_stash", "jobs"} & request.app.state.stubbed_routes
            )
        else:
            out.restart_needed = bool(
                {"library_komga", "media_komga"} & request.app.state.stubbed_routes
            )
    return out


@router.post("/{name}/test", response_model=TestOut, dependencies=[Depends(write_guard)])
def test_connection(request: Request, name: str) -> TestOut:
    store: ConnectionStore = request.app.state.connection_store
    if name not in NAMES:
        raise ApiError(404, "not_found", "unknown connection")

    address = store.address(name)
    if not address:
        return TestOut(ok=False, message="not configured")

    settings = request.app.state.settings
    transport: httpx.BaseTransport | None = getattr(request.app.state, "connection_transport", None)
    if settings.mode == "fixture" and transport is None:
        return TestOut(ok=False, message="fixture mode: no real connection")

    secret = store.effective_secret(name)
    site_auth = build_auth(name, store.field_values(name))
    if site_auth.missing:
        return TestOut(ok=False, message="missing: " + ", ".join(site_auth.missing))

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

    client = httpx.Client(transport=transport, timeout=10.0, follow_redirects=False)
    try:
        if method == "POST":
            resp = client.post(url, json=json_body, headers=headers)
        else:
            resp = client.get(url, params=params, headers=headers, auth=site_auth.basic)
    except httpx.HTTPError as exc:
        logger.warning("connection test for %s failed: %s", name, type(exc).__name__)
        return TestOut(ok=False, message="unreachable")
    finally:
        client.close()

    if resp.status_code == 200:
        return TestOut(ok=True, message="connected")
    if resp.status_code in (401, 403):
        return TestOut(ok=False, message="key rejected")
    return TestOut(ok=False, message=f"HTTP {resp.status_code}")
