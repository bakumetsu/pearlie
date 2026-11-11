from fastapi import APIRouter, Request

from app.config import Settings
from app.db import db_reachable
from app.fixtures.scenarios import active
from app.models import Health, KomgaHealth, Site, StashHealth, State
from app.update.version import current_version

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> Health:
    settings: Settings = request.app.state.settings
    db = "ok" if db_reachable(settings.db_path) else "error"
    status = "ok" if db == "ok" else "degraded"
    stash_state: State = "down" if active("offline") else "not_configured"
    return Health(
        status=status,
        version=current_version().version,
        db=db,
        stash=StashHealth(state=stash_state, version=None),
        komga=KomgaHealth(state="not_configured"),
        mounts=[],
        sites=[
            Site(id=site, state="not_configured")
            for site in ("danbooru", "gelbooru", "rule34", "nhentai")
        ],
    )
