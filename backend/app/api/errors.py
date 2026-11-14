from __future__ import annotations

from typing import Any, NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute, APIRouter
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Application-level error carrying a Problem body."""

    def __init__(self, status: int, code: str, message: str, **extra: object) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.extra: dict[str, Any] = dict(extra)


def install(app: FastAPI) -> None:
    """Register exception handlers producing the Problem JSON shape."""

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        content = {"code": exc.code, "message": exc.message, **exc.extra}
        return JSONResponse(
            status_code=exc.status, content=content, headers={"Cache-Control": "no-store"}
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail: Any = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        codes = {404: "not_found", 405: "method_not_allowed", 409: "conflict"}
        code = codes.get(exc.status_code, "error")
        message = detail if isinstance(detail, str) else "Error"
        return JSONResponse(status_code=exc.status_code, content={"code": code, "message": message})

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        if request.url.path.startswith("/api/connections"):
            err = exc.errors()[0]
            return JSONResponse(
                status_code=422,
                content={
                    "code": "invalid",
                    "message": "invalid request",
                    "field": str(err["loc"][-1]),
                },
            )
        err = exc.errors()[0]
        loc = ".".join(str(p) for p in err["loc"])
        field = str(err["loc"][-1])
        content = {"code": "invalid", "message": f"{loc}: {err['msg']}", "field": field}
        return JSONResponse(status_code=422, content=content)


def stub_router(source: APIRouter, status: int, code: str, message: str) -> APIRouter:
    """Build a router mirroring *source* paths/methods whose handlers always raise ApiError."""
    router = APIRouter()

    async def handler() -> NoReturn:
        raise ApiError(status, code, message)

    for route in source.routes:
        if not isinstance(route, APIRoute):
            continue
        router.add_api_route(
            path=route.path,
            endpoint=handler,
            methods=list(route.methods or []),
            response_model=None,
            include_in_schema=False,
        )
    return router
