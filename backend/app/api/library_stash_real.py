"""Real Stash library router – delegates to the Stash GraphQL API."""

import secrets

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.api.patch_rules import check_patch
from app.models import LibraryItem, Page, PageStats, PatchBody
from app.paging import clamp_page, clamp_page_size, pages_for
from app.targets.stash_client import StashClient, StashError
from app.targets.stash_library import (
    image_detail,
    image_item,
    list_notice,
    map_items,
    stash_sort,
    valid_id,
    video_detail,
    video_item,
)

router = APIRouter(prefix="/api")


def _up(err: StashError) -> ApiError:
    return ApiError(err.status, err.code, err.message)


def fetch_stash_page(fetch, page: int, page_size: int) -> tuple[list[dict], int, dict, int]:
    """Fetch a page; clamp *page* if out of range and re-fetch.

    *fetch* is called as ``fetch(p, page_size)``.
    Returns ``(dtos, count, agg, served)``.
    """
    dtos, count, agg = fetch(page, page_size)
    pages = pages_for(count, page_size)
    if page > max(pages, 1):
        served = clamp_page(page, pages)
        dtos, count, agg = fetch(served, page_size)
    else:
        served = page
    return dtos, count, agg, served


@router.get("/library/stash/images", response_model=Page[LibraryItem])
def list_stash_images(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    q: str = Query(""),
    sort: str = Query("newest", pattern="^(newest|rating|random)$"),
    favorite: bool | None = Query(None),
    seed: int | None = Query(None, ge=0, lt=10**8),
) -> Page[LibraryItem]:
    client: StashClient = request.app.state.stash
    page_size = clamp_page_size("stash_images", page_size)
    if sort == "random":
        seed = seed if seed is not None else secrets.randbelow(10**8)
    else:
        seed = None
    field, direction = stash_sort(sort, seed)
    try:
        dtos, count, agg, served = fetch_stash_page(
            lambda p, ps: client.list_images(p, ps, q, field, direction),
            page,
            page_size,
        )
    except StashError as e:
        raise _up(e) from None
    items, bad = map_items(dtos, image_item)
    pages = pages_for(count, page_size)
    stats = PageStats(megapixels=agg["megapixels"], size_bytes=agg["size_bytes"])
    return Page[LibraryItem](
        items=items,
        page=served,
        page_size=page_size,
        total=count,
        pages=pages,
        stats=stats,
        next_page=served + 1 if served * page_size < count else None,
        notice=list_notice(favorite, bad),
        seed=seed,
    )


@router.get("/library/stash/videos", response_model=Page[LibraryItem])
def list_stash_videos(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    q: str = Query(""),
    sort: str = Query("newest", pattern="^(newest|rating|random)$"),
    favorite: bool | None = Query(None),
    seed: int | None = Query(None, ge=0, lt=10**8),
) -> Page[LibraryItem]:
    client: StashClient = request.app.state.stash
    page_size = clamp_page_size("stash_videos", page_size)
    if sort == "random":
        seed = seed if seed is not None else secrets.randbelow(10**8)
    else:
        seed = None
    field, direction = stash_sort(sort, seed)
    try:
        dtos, count, agg, served = fetch_stash_page(
            lambda p, ps: client.list_scenes(p, ps, q, field, direction),
            page,
            page_size,
        )
    except StashError as e:
        raise _up(e) from None
    items, bad = map_items(dtos, video_item)
    pages = pages_for(count, page_size)
    stats = PageStats(megapixels=agg["megapixels"], size_bytes=agg["size_bytes"])
    return Page[LibraryItem](
        items=items,
        page=served,
        page_size=page_size,
        total=count,
        pages=pages,
        stats=stats,
        next_page=served + 1 if served * page_size < count else None,
        notice=list_notice(favorite, bad),
        seed=seed,
    )


def _link_base(request: Request) -> str:
    s = request.app.state.settings
    return s.stash_public_url or s.stash_url or ""


@router.get("/library/images/{id}")
def get_stash_image(request: Request, id: str):
    if not valid_id(id):
        raise ApiError(404, "not_found", "Item not found")
    client: StashClient = request.app.state.stash
    try:
        dto = client.get_image(id)
    except StashError as e:
        raise _up(e) from None
    if dto is None:
        raise ApiError(404, "not_found", "Item not found")
    try:
        return image_detail(dto, link_base=_link_base(request))
    except (KeyError, TypeError, ValueError):
        raise ApiError(502, "upstream_error", "Stash returned an unreadable item") from None


@router.get("/library/videos/{id}")
def get_stash_video(request: Request, id: str):
    if not valid_id(id):
        raise ApiError(404, "not_found", "Item not found")
    client: StashClient = request.app.state.stash
    try:
        dto = client.get_scene(id)
    except StashError as e:
        raise _up(e) from None
    if dto is None:
        raise ApiError(404, "not_found", "Item not found")
    try:
        return video_detail(dto, link_base=_link_base(request))
    except (KeyError, TypeError, ValueError):
        raise ApiError(502, "upstream_error", "Stash returned an unreadable item") from None


def _patch(request: Request, kind: str, id: str, body: PatchBody):
    if not valid_id(id):
        raise ApiError(404, "not_found", "Item not found")
    check_patch("Stash", body)
    if body.tags is not None:
        for tag in body.tags:
            if not tag or len(tag) > 64:
                raise ApiError(422, "invalid_tag", "Bad tag", field="tags")
    client: StashClient = request.app.state.stash
    try:
        if kind == "images":
            dto = client.get_image(id)
        else:
            dto = client.get_scene(id)
        if dto is None:
            raise ApiError(404, "not_found", "Item not found")
        fields: dict = {}
        if "rating" in body.model_fields_set:
            fields["rating100"] = None if body.rating is None else body.rating * 20
        if body.tags is not None:
            fields["tag_ids"] = client.resolve_tag_ids(body.tags)
        if fields:
            client.update_item(kind, id, fields)
        if kind == "images":
            dto = client.get_image(id)
        else:
            dto = client.get_scene(id)
        if dto is None:
            raise ApiError(404, "not_found", "Item not found")
        try:
            if kind == "images":
                return image_detail(dto, link_base=_link_base(request))
            return video_detail(dto, link_base=_link_base(request))
        except (KeyError, TypeError, ValueError):
            raise ApiError(502, "upstream_error", "Stash returned an unreadable item") from None
    except StashError as e:
        raise _up(e) from None


@router.patch("/library/images/{id}")
def patch_stash_image(request: Request, id: str, body: PatchBody):
    return _patch(request, "images", id, body)


@router.patch("/library/videos/{id}")
def patch_stash_video(request: Request, id: str, body: PatchBody):
    return _patch(request, "videos", id, body)


def _delete_handler(id: str) -> None:
    raise ApiError(501, "not_supported", "Editing and deleting Stash items is not available yet")


for _p in ("/library/images/{id}", "/library/videos/{id}"):
    router.delete(_p)(_delete_handler)
