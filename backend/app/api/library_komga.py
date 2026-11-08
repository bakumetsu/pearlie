from fastapi import APIRouter, Depends, Query

from app.api.errors import ApiError
from app.fixtures.scenarios import active, slow_dependency
from app.fixtures.store import store
from app.models import (
    LibraryItem,
    LibraryItemDetail,
    Page,
    PatchBody,
    ProgressBody,
    ProgressResult,
    TrashResult,
)

router = APIRouter(prefix="/api", dependencies=[Depends(slow_dependency)])

KINDS: dict[str, str] = {
    "komga/series": "series",
    "komga/books": "books",
}


for _p, _k in KINDS.items():

    def _factory(path: str = _p, kinds: str = _k):
        @router.get(f"/library/{path}")
        def handler(
            page: int = Query(1, ge=1),
            page_size: int = Query(60, ge=1, le=200),
            q: str = "",
            sort: str = Query("newest", pattern="^(newest|rating|random)$"),
            favorite: bool | None = None,
        ) -> Page[LibraryItem]:
            """List library items."""
            if active("empty"):
                return Page(items=[], page=page, page_size=page_size, total=0, next_page=None)
            result = store.list_library(kinds, page, page_size, q, sort, favorite)
            if result is None:
                raise ApiError(404, "not_found", "Not found")
            return result

        return handler

    _factory()


def _detail_routes(kind: str) -> None:

    @router.get(f"/library/{kind}/{{id}}")
    def get_item(id: str) -> LibraryItemDetail:
        """Get a single library item by id."""
        result = store.library_detail(kind, id)
        if result is None:
            raise ApiError(404, "not_found", "Item not found")
        return result

    @router.patch(f"/library/{kind}/{{id}}")
    def patch_item(id: str, body: PatchBody) -> LibraryItemDetail:
        """Update rating, favorite, or tags on an item."""
        if active("errors"):
            raise ApiError(502, "upstream_error", "Stash returned 502")
        rating_set = "rating" in body.model_fields_set
        try:
            result = store.patch(kind, id, rating_set, body.rating, body.favorite, body.tags)
        except ValueError:
            raise ApiError(422, "invalid_tag", "Bad tag", field="tags") from None
        if result is None:
            raise ApiError(404, "not_found", "Item not found")
        return result

    @router.delete(f"/library/{kind}/{{id}}")
    def delete_item(id: str) -> TrashResult:
        """Move an item to trash."""
        result = store.delete(kind, id)
        if result is None:
            raise ApiError(404, "not_found", "Item not found")
        return result


for _kind in ("series", "books"):
    _detail_routes(_kind)


@router.post("/library/komga/books/{id}/progress")
def set_progress(id: str, body: ProgressBody) -> ProgressResult:
    """Update reading progress for a book."""
    result = store.set_progress(id, body.page)
    if result is None:
        raise ApiError(404, "not_found", "Item not found")
    return result
