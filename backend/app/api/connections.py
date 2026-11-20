"""Connections router: manage per-connection addresses and secrets."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, SecretStr, StrictBool

from app.api.errors import ApiError
from app.api.guard import write_guard
from app.api.health import clear_health_cache
from app.connection_probe import probe_connection
from app.connections_store import (
    DISPLAY_PRIMARY,
    FIELDS,
    FIXED_HOSTS,
    NAMES,
    ConnectionStore,
    StoreError,
)
from app.sources.nhentai import NHentai

router = APIRouter(prefix="/api/connections")

NhentaiAuth = Literal["guest", "ok", "failed", "unchecked"]
NhentaiReason = Literal["invalid", "blocked"]


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
    auth: NhentaiAuth | None = None
    reason: NhentaiReason | None = None


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


def _nhentai_auth(request: Request) -> tuple[NhentaiAuth, NhentaiReason | None]:
    """Key state of the nhentai adapter as (auth, reason); never the key itself."""
    source = getattr(request.app.state, "sources", {}).get("nhentai")
    if not isinstance(source, NHentai):
        return "guest", None
    state, reason = source.key_state
    if state == "ok":
        return "ok", None
    if state == "unchecked":
        return "unchecked", None
    if state == "failed":
        return "failed", "blocked" if reason == "blocked" else "invalid"
    return "guest", None


def _build_out(name: str, store: ConnectionStore, request: Request) -> ConnectionOut:
    locked = store.env_locked(name)
    auth, reason = _nhentai_auth(request) if name == "nhentai" else (None, None)
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
                primary=DISPLAY_PRIMARY[name] == f.id,
            )
            for f in FIELDS[name]
        ],
        auth=auth,
        reason=reason,
    )


@router.get("", response_model=ConnectionsOut)
def get_connections(request: Request) -> ConnectionsOut:
    store: ConnectionStore = request.app.state.connection_store
    connections = [_build_out(name, store, request) for name in NAMES]
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
    out = _build_out(name, store, request)
    clear_health_cache(request.app)
    if name in ("stash", "stump"):
        from app.main import rebuild_client

        rebuild_client(request.app, name)
    return out


@router.post("/{name}/test", response_model=TestOut, dependencies=[Depends(write_guard)])
def test_connection(request: Request, name: str) -> TestOut:
    if name not in NAMES:
        raise ApiError(404, "not_found", "unknown connection")

    if name == "nhentai":
        checked = _test_nhentai_key(request)
        if checked is not None:
            return checked
    result = probe_connection(request.app, name)
    return TestOut(ok=result.ok, message=result.message)


_KEY_MESSAGES = {
    ("ok", ""): (True, "Key works"),
    ("failed", "invalid"): (False, "Key rejected by nhentai"),
    ("failed", "blocked"): (False, "nhentai blocked this key. Try again later."),
}


def _test_nhentai_key(request: Request) -> TestOut | None:
    """Run the GET /user key check; None when there is no key or no real site call."""
    if request.app.state.settings.mode == "fixture":
        return None
    source = getattr(request.app.state, "sources", {}).get("nhentai")
    if not isinstance(source, NHentai):
        return None
    state = source.check_key()
    if state[0] == "unset":
        return None
    ok, message = _KEY_MESSAGES.get(state, (False, "nhentai unreachable"))
    clear_health_cache(request.app)
    return TestOut(ok=ok, message=message)
