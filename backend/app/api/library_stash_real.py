"""Real Stash library router – delegates to the Stash GraphQL API."""

import secrets

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.models import LibraryItem, Page, PatchBody
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
    if sort == "random":
        seed = seed if seed is not None else secrets.randbelow(10**8)
    else:
        seed = None
    field, direction = stash_sort(sort, seed)
    try:
        dtos, count = client.list_images(page, page_size, q, field, direction)
    except StashError as e:
        raise _up(e) from None
    items, bad = map_items(dtos, image_item)
    return Page[LibraryItem](
        items=items,
        page=page,
        page_size=page_size,
        total=count,
        next_page=page + 1 if page * page_size < count else None,
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
    if sort == "random":
        seed = seed if seed is not None else secrets.randbelow(10**8)
    else:
        seed = None
    field, direction = stash_sort(sort, seed)
    try:
        dtos, count = client.list_scenes(page, page_size, q, field, direction)
    except StashError as e:
        raise _up(e) from None
    items, bad = map_items(dtos, video_item)
    return Page[LibraryItem](
        items=items,
        page=page,
        page_size=page_size,
        total=count,
        next_page=page + 1 if page * page_size < count else None,
        notice=list_notice(favorite, bad),
        seed=seed,
    )


@router.get("/library/stash/images/{id}")
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
        return image_detail(dto)
    except (KeyError, TypeError, ValueError):
        raise ApiError(502, "upstream_error", "Stash returned an unreadable item") from None


@router.get("/library/stash/videos/{id}")
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
        return video_detail(dto)
    except (KeyError, TypeError, ValueError):
        raise ApiError(502, "upstream_error", "Stash returned an unreadable item") from None


def _patch_handler(id: str, body: PatchBody) -> None:
    raise ApiError(501, "not_supported", "Editing and deleting Stash items is not available yet")


def _delete_handler(id: str) -> None:
    raise ApiError(501, "not_supported", "Editing and deleting Stash items is not available yet")


for _p in ("/library/stash/images/{id}", "/library/stash/videos/{id}"):
    router.patch(_p)(_patch_handler)
    router.delete(_p)(_delete_handler)
