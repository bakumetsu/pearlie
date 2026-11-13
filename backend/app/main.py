import asyncio
import logging
import random
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr

from app import logs
from app.api import (
    connections,
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
    search_filters,
    search_real,
    site_icons,
    tabs,
    trash,
    update,
    view_settings,
)
from app.api import fixture as fixture_api
from app.api import logs as logs_api
from app.api.errors import install as install_errors
from app.api.errors import stub_router
from app.api.guard import mutation_guard
from app.api.health import router as health_router
from app.config import ConfigError, Settings, load_settings
from app.connections_store import ConnectionStore
from app.db import connect, init_db
from app.jobs.worker import JobWorker
from app.komga import Komga
from app.logs import install_http_hooks
from app.sources.base import Source
from app.sources.danbooru import Danbooru
from app.sources.dapi import Gelbooru, Rule34
from app.sources.nhentai import NHentai
from app.sources.throttle import DEFAULT_PACE, Throttle
from app.targets.komga import KomgaTarget
from app.targets.stash import StashTarget
from app.targets.stash_client import StashClient
from app.update import runner
from app.update.changelog import Changelog, FakeChangelog
from app.update.check import FakeChecker, UpdateChecker
from app.update.version import current_version

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


def _with_stored_connections(settings: Settings, store: ConnectionStore) -> Settings:
    stash_url = store.address("stash")
    stash_key = store.effective_secret("stash")
    komga_url = store.address("komga")
    komga_key = store.effective_secret("komga")
    updates: dict[str, object] = {}
    if stash_url and stash_url != settings.stash_url:
        updates["stash_url"] = stash_url
    # A changed address drops the env key; only the key typed for it may go there.
    if (stash_key or "stash_url" in updates) and (
        stash_key != settings.stash_api_key.get_secret_value()
    ):
        updates["stash_api_key"] = SecretStr(stash_key)
    if komga_url and komga_url != settings.komga_url:
        updates["komga_url"] = komga_url
    if (komga_key or "komga_url" in updates) and (
        komga_key != settings.komga_api_key.get_secret_value()
    ):
        updates["komga_api_key"] = SecretStr(komga_key)
    if updates:
        return settings.model_copy(update=updates)
    return settings


async def _daily_update_check(app_: FastAPI) -> None:
    await asyncio.sleep(random.uniform(0, 86400))
    while True:
        try:
            with connect(app_.state.settings.db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = 'update.check'"
                ).fetchone()
            if (row[0] if row else "on") != "off":
                with connect(app_.state.settings.db_path) as conn:
                    row = conn.execute(
                        "SELECT value FROM settings WHERE key = 'update.channel'"
                    ).fetchone()
                channel = row[0] if row else "main"
                if channel not in ("main", "dev"):
                    channel = "main"
                await asyncio.to_thread(app_.state.update_checker.check, channel)
        except Exception:
            logger.warning("daily update check failed")
        await asyncio.sleep(86400)


def _build_stash(settings: Settings) -> StashClient | None:
    if not settings.stash_url:
        return None
    return StashClient(settings.stash_url, settings.stash_api_key.get_secret_value())


def _build_komga(settings: Settings) -> Komga | None:
    if not settings.komga_url:
        return None
    return Komga(settings.komga_url, settings.komga_api_key.get_secret_value())


def rebuild_client(app: FastAPI, name: str) -> None:
    if app.state.settings.mode == "fixture":
        return
    settings = _with_stored_connections(app.state.settings, app.state.connection_store)
    app.state.settings = settings
    if name == "komga":
        app.state.komga = _build_komga(settings)
        komga_target = getattr(app.state, "komga_target", None)
        if komga_target is not None and app.state.komga is not None:
            komga_target.set_client(app.state.komga)
    elif name == "stash":
        app.state.stash = _build_stash(settings)
        worker = getattr(app.state, "worker", None)
        stash_target = getattr(app.state, "stash_target", None)
        if worker is not None and stash_target is not None and app.state.stash is not None:
            stash_target.set_client(app.state.stash)


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    init_db(settings.db_path)
    # httpx logs full request URLs at INFO, and some Test calls carry api_key in the query.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logs.register_settings_secrets(settings)
    logs.setup_logging(
        settings.log_dir or settings.db_path.parent / "logs",
        debug=logs.read_debug_setting(settings.db_path),
        keep_days=settings.log_keep_days,
    )
    logger.info(settings.safe_summary())
    worker_enabled = settings.worker_enabled

    @asynccontextmanager
    async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
        worker: JobWorker | None = getattr(app_.state, "worker", None)
        if worker is not None and worker_enabled:
            worker.start()
        daily: asyncio.Task[None] | None = None
        if app_.state.settings.mode == "real":
            daily = asyncio.create_task(_daily_update_check(app_))
        try:
            yield
        finally:
            if daily is not None:
                daily.cancel()
            if worker is not None and worker_enabled:
                worker.stop()
            client: httpx.Client | None = getattr(app_.state, "http", None)
            if client is not None:
                client.close()
            update_http: httpx.Client | None = getattr(app_.state, "update_http", None)
            if update_http is not None:
                update_http.close()

    app = FastAPI(lifespan=lifespan, dependencies=[Depends(mutation_guard)])
    install_errors(app)
    app.state.settings = settings
    app.state.update_root = runner.LAYOUT_ROOT
    app.state.update_run = subprocess.run
    app.state.update_http = None
    if settings.mode == "fixture":
        app.state.update_checker = FakeChecker()
        app.state.update_changelog = FakeChangelog()
    else:
        http = install_http_hooks(httpx.Client(timeout=5.0), "update")
        app.state.update_http = http
        app.state.update_checker = UpdateChecker(
            http, settings.db_path, f"Pearlie/{current_version().version}"
        )
        app.state.update_changelog = Changelog(
            http, settings.db_path, f"Pearlie/{current_version().version}"
        )
    app.state.connections_mem = {}
    # Built on the original settings on purpose: the store needs the .env view,
    # while app.state.settings below may be replaced by a stored-values copy.
    app.state.connection_store = ConnectionStore(settings, app.state.connections_mem)
    logs.register_stored_connections(app.state.connection_store)
    app.state.connection_transport = None
    throttles: dict[str, Throttle] = {
        site: Throttle(DEFAULT_PACE[site], site=site) for site in DEFAULT_PACE
    }
    app.state.throttles = throttles
    danbooru = Danbooru(
        throttle=throttles["danbooru"],
        credentials=lambda: app.state.connection_store.field_values("danbooru"),
    )
    sources: dict[str, Source] = {
        "danbooru": danbooru,
        "rule34": Rule34(
            throttle=throttles["rule34"],
            credentials=lambda: app.state.connection_store.field_values("rule34"),
        ),
        "gelbooru": Gelbooru(
            throttle=throttles["gelbooru"],
            credentials=lambda: app.state.connection_store.field_values("gelbooru"),
        ),
        "nhentai": NHentai(
            throttle=throttles["nhentai"],
            credentials=lambda: app.state.connection_store.field_values("nhentai"),
        ),
    }
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
    if settings.mode == "real":
        settings = _with_stored_connections(settings, app.state.connection_store)
        app.state.settings = settings
    komga_ok = bool(settings.komga_url)
    stash_ok = bool(settings.stash_url)
    app.state.komga = _build_komga(settings) if settings.mode != "fixture" else None
    app.state.stash = _build_stash(settings) if settings.mode != "fixture" else None

    app.state.worker = None
    app.state.http = None
    app.state.stash_target = None
    app.state.komga_target = None
    stash_on = stash_ok and app.state.stash is not None
    komga_on = komga_ok and app.state.komga is not None
    if "jobs" in real and (stash_on or komga_on):
        http = install_http_hooks(httpx.Client(), "download", save=True)
        app.state.http = http
        targets: dict = {}
        hooks = []
        if app.state.stash is not None:
            stash_target = StashTarget(
                settings, app.state.stash, http, app.state.sources, throttles=throttles
            )
            app.state.stash_target = stash_target
            targets["stash"] = stash_target
            hooks.append(stash_target.cleanup_temp)
        if app.state.komga is not None:
            komga_target = KomgaTarget(
                settings, app.state.komga, http, app.state.sources, throttles=throttles
            )
            app.state.komga_target = komga_target
            targets["komga"] = komga_target
            hooks.append(komga_target.cleanup_temp)
        app.state.worker = JobWorker(
            settings.db_path,
            app.state.sources,
            targets,
            interval_s=settings.download_interval_s,
            startup_hooks=hooks,
        )

    komga_names = {"library_komga", "media_komga"}
    stash_names = {"library_stash", "media_stash"}
    stubbed: set[str] = set()
    for name in real:
        unconfigured = (
            (name in komga_names and not komga_ok)
            or (name in stash_names and not stash_ok)
            or (name == "jobs" and not (stash_ok or komga_ok))
        )
        if unconfigured:
            app.include_router(
                stub_router(REAL_ROUTERS[name], 503, "not_configured", f"{name} is not configured")
            )
            stubbed.add(name)
        else:
            app.include_router(REAL_ROUTERS[name])
    app.state.stubbed_routes = stubbed
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

    app.include_router(search_filters.router)
    app.include_router(destinations.router)
    app.include_router(view_settings.router)
    app.include_router(tabs.router)
    app.include_router(logs_api.router)
    app.include_router(player_settings.router)
    app.include_router(options.router)
    app.include_router(connections.router)
    app.include_router(site_icons.router)
    app.include_router(update.router)
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
