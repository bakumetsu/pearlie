import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.config import ConfigError, Settings, load_settings
from app.db import init_db

logger = logging.getLogger("pearlie")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    init_db(settings.db_path)
    logger.info(settings.safe_summary())
    app = FastAPI()
    app.state.settings = settings
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
