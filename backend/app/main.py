import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    destinations,
    jobs,
    jobs_real,
    library_komga,
    library_komga_real,
    library_stash,
    library_stash_real,
    media_komga,
    media_komga_real,
    media_stash,
    media_stash_real,
    options,
    player_settings,
    rules,
    rules_real,
    search,
    search_real,
    trash,
    view_settings,
)
from app.api import fixture as fixture_api
from app.api.errors import install as install_errors
from app.api.errors import stub_router
from app.api.health import router as health_router
from app.config import ConfigError, Settings, load_settings
from app.db import init_db
from app.jobs.worker import JobWorker
from app.komga import Komga
from app.sources.base import Source
from app.sources.danbooru import Danbooru
from app.sources.throttle import DEFAULT_PACE, Throttle
from app.targets.stash import StashTarget
from app.targets.stash_client import StashClient

FIXTURE_ROUTERS = {
    "search": search.router,
    "library_komga": library_komga.router,
    "library_stash": library_stash.router,
    "media_stash": media_stash.router,
    "media_komga": media_komga.router,
    "jobs": jobs.router,
    "rules": rules.router,
    "trash": trash.router,
}
REAL_ROUTERS: dict[str, APIRouter] = {
    "search": search_real.router,
    "library_komga": library_komga_real.router,
    "media_stash": media_stash_real.router,
    "library_stash": library_stash_real.router,
    "media_komga": media_komga_real.router,
    "jobs": jobs_real.router,
    "rules": rules_real.router,
}

logger = logging.getLogger("pearlie")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    init_db(settings.db_path)
    logger.info(settings.safe_summary())

    @asynccontextmanager
    async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
        worker: JobWorker | None = getattr(app_.state, "worker", None)
        if worker is not None and settings.worker_enabled:
            worker.start()
        try:
            yield
        finally:
            if worker is not None and settings.worker_enabled:
                worker.stop()
            client: httpx.Client | None = getattr(app_.state, "http", None)
            if client is not None:
                client.close()

    app = FastAPI(lifespan=lifespan)
    install_errors(app)
    app.state.settings = settings
    throttles: dict[str, Throttle] = {site: Throttle(DEFAULT_PACE[site]) for site in DEFAULT_PACE}
    app.state.throttles = throttles
    sources: dict[str, Source] = {"danbooru": Danbooru(throttle=throttles["danbooru"])}
    app.state.sources = sources
    options.apply_pace(app)

    if settings.mode == "fixture":
        real = {n.strip() for n in settings.real.split(",") if n.strip()}
        if real:
            logger.warning("fixture mode: PEARLIE_REAL ignored (%s)", ", ".join(sorted(real)))
            real = set()
    else:
        real = set(REAL_ROUTERS)
        if settings.real.strip():
            logger.warning("PEARLIE_REAL is ignored (all routes mount in real mode)")
    komga_ok = bool(settings.komga_url)
    stash_ok = bool(settings.stash_url)
    app.state.komga = (
        Komga(settings.komga_url, settings.komga_api_key.get_secret_value())
        if komga_ok and settings.mode != "fixture"
        else None
    )

    app.state.stash = (
        StashClient(settings.stash_url, settings.stash_api_key.get_secret_value())
        if settings.stash_url and settings.mode != "fixture"
        else None
    )

    app.state.worker = None
    app.state.http = None
    if "jobs" in real and stash_ok and app.state.stash is not None:
        http = httpx.Client()
        app.state.http = http
        stash_target = StashTarget(settings, app.state.stash, http, app.state.sources, throttles=throttles)
        app.state.worker = JobWorker(
            settings.db_path,
            app.state.sources,
            {"stash": stash_target},
            interval_s=settings.download_interval_s,
            startup_hooks=[stash_target.cleanup_temp],
        )

    komga_names = {"library_komga", "media_komga"}
    stash_names = {"library_stash", "media_stash", "jobs"}
    stubbed: set[str] = set()
    for name in real:
        if (name in komga_names and not komga_ok) or (name in stash_names and not stash_ok):
            app.include_router(
                stub_router(REAL_ROUTERS[name], 503, "not_configured", f"{name} is not configured")
            )
            stubbed.add(name)
        else:
            app.include_router(REAL_ROUTERS[name])
    if stubbed:
        logger.warning("not configured, answering 503: %s", ", ".join(sorted(stubbed)))
    if settings.mode == "real":
        for name, router in FIXTURE_ROUTERS.items():
            if name not in REAL_ROUTERS:
                app.include_router(
                    stub_router(
                        router, 501, "not_implemented", f"{name} is not available in real mode yet"
                    )
                )

    mounted_fixture: set[str] = set()
    if settings.mode == "fixture":
        for name, router in FIXTURE_ROUTERS.items():
            if name not in real:
                app.include_router(router)
                mounted_fixture.add(name)
    fixture_on = bool(mounted_fixture)
    if fixture_on:
        app.include_router(fixture_api.router)
    app.state.fixture_routers = mounted_fixture

    app.include_router(destinations.router)
    app.include_router(view_settings.router)
    app.include_router(player_settings.router)
    app.include_router(options.router)
    app.include_router(health_router)

    static_dir: Path = settings.static_dir
    index_html = static_dir / "index.html"
    if index_html.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}")
        def catch_all(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404)
            return FileResponse(index_html)

    return app


def run() -> None:
    try:
        settings = load_settings()
    except ConfigError as err:
        raise SystemExit(str(err)) from None
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
