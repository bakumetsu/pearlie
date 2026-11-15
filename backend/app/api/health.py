import time

from fastapi import APIRouter, FastAPI, Request

from app.config import Settings
from app.connection_probe import probe_connection
from app.connections_store import ConnectionStore
from app.db import db_reachable
from app.fixtures.scenarios import active
from app.models import Health, KomgaHealth, Site, StashHealth, State
from app.sources.auth import build_auth
from app.update.version import current_version

router = APIRouter(prefix="/api")

CACHE_SECONDS = 30.0
SITES = ("danbooru", "gelbooru", "rule34", "nhentai")


def clear_health_cache(app: FastAPI) -> None:
    app.state.health_cache = {}


def _service(app: FastAPI, name: str) -> tuple[State, str | None]:
    """State and version of Stash or Komga; the probe result is cached briefly."""
    store: ConnectionStore = app.state.connection_store
    address = store.address(name)
    if not address:
        return "not_configured", None
    cache: dict[str, tuple[float, str, State, str | None]] = getattr(app.state, "health_cache", {})
    app.state.health_cache = cache
    hit = cache.get(name)
    now = time.monotonic()
    if hit and hit[1] == address and now - hit[0] < CACHE_SECONDS:
        return hit[2], hit[3]
    result = probe_connection(app, name)
    state: State = "ok" if result.ok else "down"
    cache[name] = (now, address, state, result.version)
    return state, result.version


def _site_state(app: FastAPI, name: str) -> State:
    """A site counts as ok when it is configured; health never calls the sites.

    Site hosts are fixed and credentials are optional, so only a half-filled pair is unconfigured.
    """
    store: ConnectionStore = app.state.connection_store
    if not store.address(name) or build_auth(name, store.field_values(name)).missing:
        return "not_configured"
    return "ok"


@router.get("/health")
def health(request: Request) -> Health:
    app = request.app
    settings: Settings = app.state.settings
    db = "ok" if db_reachable(settings.db_path) else "error"
    status = "ok" if db == "ok" else "degraded"
    fixture = (
        settings.mode == "fixture" and getattr(app.state, "connection_transport", None) is None
    )
    if fixture:
        # Fixture mode has no real connection to probe: report configuration only.
        store: ConnectionStore = app.state.connection_store
        stash_state: State = "ok" if store.address("stash") else "not_configured"
        komga_state: State = "ok" if store.address("komga") else "not_configured"
        stash_version = komga_version = None
    else:
        stash_state, stash_version = _service(app, "stash")
        komga_state, komga_version = _service(app, "komga")
    if active("offline"):
        stash_state = "down"
    return Health(
        status=status,
        version=current_version().version,
        db=db,
        stash=StashHealth(state=stash_state, version=stash_version),
        komga=KomgaHealth(state=komga_state, version=komga_version),
        mounts=[],
        sites=[Site(id=site, state=_site_state(app, site)) for site in SITES],
    )
