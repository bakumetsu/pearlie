from fastapi import APIRouter, Request

from app.config import Settings
from app.db import db_reachable

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict:
    settings: Settings = request.app.state.settings
    db = "ok" if db_reachable(settings.db_path) else "error"
    status = "ok" if db == "ok" else "degraded"
    return {
        "status": status,
        "db": db,
        "stash": {"state": "not_configured", "version": None},
        "komga": {"state": "not_configured", "version": None},
        "mounts": [],
        "sites": [
            {"id": site, "state": "not_configured"}
            for site in ("danbooru", "gelbooru", "rule34", "nhentai")
        ],
    }
