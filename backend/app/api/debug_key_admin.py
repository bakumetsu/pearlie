"""Admin API for the debug key: browser only, behind the proxy login (D-34)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from app import debug_key
from app.api.guard import write_guard

router = APIRouter(prefix="/api/options/debug-key")


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttl: Literal["1h", "24h", "7d"]


class DebugKeyStatus(BaseModel):
    state: Literal["off", "active", "expired"]
    id: str | None
    created_at: str | None
    expires_at: str | None
    last_used_at: str | None
    uses_approx: int


class CreatedKey(BaseModel):
    key: str
    id: str
    expires_at: str


@router.get("")
def get_status(request: Request, response: Response) -> DebugKeyStatus:
    response.headers["Cache-Control"] = "no-store"
    record = debug_key.read_record(request.app.state.settings.db_path)
    return DebugKeyStatus(**debug_key.key_status(record))


@router.post("", dependencies=[Depends(write_guard)])
def create(request: Request, body: CreateBody, response: Response) -> CreatedKey:
    key, record = debug_key.create_key(request.app.state.settings.db_path, body.ttl)
    response.headers["Cache-Control"] = "no-store"
    return CreatedKey(key=key, id=record["id"], expires_at=record["expires_at"])


@router.delete("", status_code=204)
def revoke(request: Request) -> Response:
    debug_key.revoke_key(request.app.state.settings.db_path)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
