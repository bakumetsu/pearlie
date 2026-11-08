"""Pydantic v2 models for the Pearlie backend API."""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, Field

Kind = Literal["image", "video", "series", "book"]
WebSource = Literal["danbooru", "gelbooru", "rule34", "nhentai"]
Target = Literal["stash", "komga"]
SectionId = Literal[
    "stash_images",
    "stash_videos",
    "komga_books",
    "danbooru",
    "gelbooru",
    "rule34",
    "nhentai",
]
JobState = Literal["queued", "running", "done", "failed", "needs_click", "skipped"]
State = Literal["ok", "down", "not_configured"]
MappingTo = Literal[
    "stash_tag",
    "comicinfo:Tags",
    "comicinfo:Genre",
    "comicinfo:Writer",
    "comicinfo:Series",
]
Decision = Literal["allow", "warn", "reject", "require_missing"]
Layer = Literal["base", "reject", "require", "warn"]


class Tag(BaseModel):
    name: str
    scope: str | None = None


class Blur(BaseModel):
    tag: str


class Problem(BaseModel):
    code: str
    message: str


class SavedRef(BaseModel):
    kind: Kind
    id: str


class LibraryItem(BaseModel):
    kind: Kind
    id: str
    title: str
    thumb_url: str
    rating: int | None = Field(default=None, ge=1, le=5)
    favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    page_count: int | None = None
    read_page: int | None = None
    book_count: int | None = None
    read_count: int | None = None
    blur: Blur | None = None
    added_at: str


class LibraryItemDetail(LibraryItem):
    tags: list[Tag] = Field(default_factory=list)
    full_url: str | None = None
    stream_url: str | None = None
    mime: str | None = None
    books: list[LibraryItem] = Field(default_factory=list)
    notice: Problem | None = None
    source_url_text: str | None = None
    page_url: str | None = Field(
        default=None,
        description=(
            "Book detail only. URL template with a "
            "literal {n} placeholder for the 1-based "
            "page number, e.g. /api/media/komga/books/7/"
            "pages/{n}. Replace {n} to get a page image."
        ),
    )


class WebItem(BaseModel):
    source: WebSource
    post_id: str
    thumb_url: str
    preview_url: str
    title: str | None = None
    tags: list[Tag] = Field(default_factory=list)
    width: int
    height: int
    page_count: int | None = None
    target: Target
    saved: SavedRef | None = None
    blur: Blur | None = None


class Section(BaseModel):
    id: SectionId
    title: str
    total: int | None = None
    items: list[LibraryItem | WebItem] = Field(default_factory=list)
    hidden: int = 0
    next_page: int | None = None
    error: Problem | None = None


T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    next_page: int | None = None
    notice: Problem | None = None


class SearchResponse(BaseModel):
    query: str
    sections: list[Section] = Field(default_factory=list)


class Job(BaseModel):
    id: str
    source: WebSource
    post_id: str
    title: str
    thumb_url: str
    target: Target
    state: JobState
    progress: float = 0.0
    eta_s: float | None = None
    error: str | None = None
    library_ref: SavedRef | None = None
    created_at: str
    finished_at: str | None = None


class JobList(BaseModel):
    items: list[Job] = Field(default_factory=list)


class PatchBody(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    favorite: bool | None = None
    tags: list[str] | None = None


class TrashItem(BaseModel):
    kind: Kind
    id: str
    title: str


class TrashResult(BaseModel):
    token: str
    expires_at: str
    retention_days: int
    item: TrashItem


class RestoreResult(BaseModel):
    item: LibraryItem


class ProgressBody(BaseModel):
    page: int


class ProgressResult(BaseModel):
    page: int
    completed: bool


class SaveBody(BaseModel):
    source: WebSource
    post_id: str


class SaveAccepted(BaseModel):
    job_id: str


class ScenarioBody(BaseModel):
    name: str


class RuleMapping(BaseModel):
    pattern: str
    to: MappingTo


class BaseList(BaseModel):
    read_only: Literal[True] = True
    tags: list[str] = Field(default_factory=list)


class RulesBody(BaseModel):
    version: int
    base_list: BaseList
    reject: list[str] = Field(default_factory=list)
    warn: list[str] = Field(default_factory=list)
    require: list[str] = Field(default_factory=list)
    mapping: list[RuleMapping] = Field(default_factory=list)


class RulesPut(BaseModel):
    version: int
    reject: list[str] = Field(default_factory=list)
    warn: list[str] = Field(default_factory=list)
    require: list[str] = Field(default_factory=list)
    mapping: list[RuleMapping] = Field(default_factory=list)


class RulesTestBody(BaseModel):
    tags: list[str] = Field(default_factory=list)


class RulesTestResult(BaseModel):
    decision: Decision
    layer: Layer | None = None
    rule: str | None = None


class StashHealth(BaseModel):
    state: State
    version: str | None = None


class KomgaHealth(BaseModel):
    state: State
    version: str | None = None


class Mount(BaseModel):
    name: str
    state: State


class Site(BaseModel):
    id: str
    state: State


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    stash: StashHealth
    komga: KomgaHealth
    db: Literal["ok", "error"] = "ok"
    mounts: list[Mount] = Field(default_factory=list)
    sites: list[Site] = Field(default_factory=list)
