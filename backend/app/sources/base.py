from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

Rating = Literal["general", "sensitive", "questionable", "explicit"]


class Post(BaseModel):
    source: str
    post_id: str
    md5: str | None = None
    file_url: str | None = None
    preview_url: str | None = None
    width: int = 0
    height: int = 0
    rating: Rating | None = None
    tags: dict[str, list[str]] = Field(default_factory=dict)
    source_url: str | None = None


class SearchPage(BaseModel):
    posts: list[Post]
    page: int
    next_page: int | None = None
    total: int | None = None
    pages: int | None = None
    dropped: list[str] = Field(default_factory=list)  # tags past the cap that cannot be applied


class SourceError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class Source(Protocol):
    id: str
    target: str  # "stash" or "komga": where saves of this source go
    file_hosts: tuple[str, ...]  # hosts a post's file_url may point to

    def search(
        self, tags: list[str], page: int = 1, page_size: int | None = None
    ) -> SearchPage: ...
    def get_post(self, post_id: str) -> Post: ...
