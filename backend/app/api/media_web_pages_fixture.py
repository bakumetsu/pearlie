"""Fixture twin of media_web_pages: same paths, local sample images, no network."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app.api.errors import ApiError
from app.api.media_stash import _ensure, _file, _n
from app.api.media_web_pages import PAGE_CACHE_CONTROL
from app.fixtures.mediagen import media_dir
from app.fixtures.store import store
from app.models import Tag, WebBook, WebItem
from app.sources.title import parse_title

router = APIRouter(prefix="/api/media/web/nhentai")
DEFAULT_PAGES = 18


def _raw(gid: str) -> dict:
    raw = store.web_raw("nhentai", gid)
    if raw is None or "_rejected" in raw:
        raise ApiError(404, "not_found", "Gallery not found")
    return raw


def _pages(raw: dict) -> int:
    count = raw.get("page_count")
    return count if isinstance(count, int) and count > 0 else DEFAULT_PAGES


def _page_file(gid: str, n: int, thumb: bool) -> FileResponse:
    _ensure()
    if not 1 <= n <= _pages(_raw(gid)):
        raise ApiError(404, "not_found", "Page not found")
    name = f"{(_n(gid) + n) % 40}{'_thumb' if thumb else ''}.jpg"
    resp = _file(media_dir() / "images" / name, "image/jpeg")
    resp.headers["Cache-Control"] = PAGE_CACHE_CONTROL
    return resp


@router.get("/{gid}/book", response_model=WebBook)
def book(request: Request, gid: str) -> JSONResponse:
    raw = _raw(gid)
    item = store.web_get("nhentai", gid)
    if item is None:
        raise ApiError(404, "not_found", "Gallery not found")
    count = _pages(raw)
    parsed = parse_title(str(raw.get("title") or ""), None)
    base = f"/api/media/web/nhentai/{gid}/pages/{{n}}"
    item = WebItem(**{**item.model_dump(), "page_count": count})
    tags: dict[str, list[str]] = {}
    for t in item.tags:
        tags.setdefault(t.scope or "general", []).append(Tag(name=t.name).name)
    data = WebBook(
        title=item.title,
        title_main=parsed.title_main or f"Gallery {gid}",
        title_sub=parsed.title_sub,
        artist=parsed.artist,
        circle=parsed.circle,
        event=parsed.event,
        language=parsed.language,
        translator=parsed.translator,
        tags=tags,
        page_count=count,
        page_url=base,
        page_thumb_url=base + "/thumb",
        item=item,
    )
    return JSONResponse(data.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.get("/{gid}/pages/{n}/thumb")
def page_thumb(gid: str, n: int) -> FileResponse:
    return _page_file(gid, n, True)


@router.get("/{gid}/pages/{n}")
def page(gid: str, n: int) -> FileResponse:
    return _page_file(gid, n, False)
