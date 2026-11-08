from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
        return JSONResponse(status_code=exc.status, content=content)

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
        err = exc.errors()[0]
        loc = ".".join(str(p) for p in err["loc"])
        field = str(err["loc"][-1])
        content = {"code": "invalid", "message": f"{loc}: {err['msg']}", "field": field}
        return JSONResponse(status_code=422, content=content)
