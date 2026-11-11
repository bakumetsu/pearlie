"""Player settings router: autoplay."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, StrictBool

from app.db import connect

router = APIRouter(prefix="/api")


class PlayerSettings(BaseModel):
    autoplay: StrictBool


@router.get("/player-settings", response_model=PlayerSettings)
def get_player_settings(request: Request) -> PlayerSettings:
    if request.app.state.settings.mode == "fixture":
        mem: dict[str, str] | None = getattr(
            request.app.state, "player_settings_mem", None
        )
        if mem is None:
            mem = {}
        autoplay = mem.get("player.autoplay", "0") == "1"
    else:
        conn = connect(request.app.state.settings.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'player.autoplay'"
            ).fetchone()
        finally:
            conn.close()
        autoplay = row["value"] == "1" if row is not None else False
    return PlayerSettings(autoplay=autoplay)


@router.put("/player-settings", response_model=PlayerSettings)
def put_player_settings(request: Request, body: PlayerSettings) -> PlayerSettings:
    value = "1" if body.autoplay else "0"
    if request.app.state.settings.mode == "fixture":
        mem: dict[str, str] | None = getattr(
            request.app.state, "player_settings_mem", None
        )
        if mem is None:
            mem = {}
            request.app.state.player_settings_mem = mem
        mem["player.autoplay"] = value
    else:
        conn = connect(request.app.state.settings.db_path)
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("player.autoplay", value),
            )
            conn.commit()
        finally:
            conn.close()
    return PlayerSettings(autoplay=body.autoplay)
