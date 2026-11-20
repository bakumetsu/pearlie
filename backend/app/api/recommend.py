"""Recommendations and Random for the book pages (D-36 section 3). Read-only, same source only.

Stump candidates come from the cached library walk (`tagged_books("", [])`, memory only).
Web candidates come from one cached search page (rule 5: through the cache and the throttle).
"""

from __future__ import annotations

import logging
import math
import random
import typing
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.errors import ApiError
from app.api.media_web_real import _authorize, proxy_path, remember
from app.api.search_filters import parse_order, parse_rating
from app.api.search_real import _cache_of
from app.bookserver.base import BookDTO, BookServerError
from app.bookserver.factory import book_server_of
from app.bookserver.map import book_item
from app.bookserver.people import book_author, title_people
from app.filters.rules import RuleSet, evaluate, load_rules
from app.filters.safe_mode import is_hidden_in_safe_mode, resolve_safe
from app.jobs.store import JobStore
from app.models import Blur, SavedRef
from app.sources.base import Post, Source, SourceError

router = APIRouter(prefix="/api")
_log = logging.getLogger(__name__)

# Tuned in tests/test_recommend.py on a pool like the live Stump (215 books, 332 tags, generic
# tags on ~87% of the books): at 6.0 about 40% of the pool passed on overlap noise, at 12.0 only
# true neighbours do (live top score: 25.9 for 11 shared tags of 22). A seed with few tags cannot
# reach 12, so the floor is also capped at MIN_SHARE of the seed's own total weight.
MIN_SCORE = 12.0
MIN_SHARE = 0.4
DEFAULT_LIMIT = 6
MAX_LIMIT = 20
SEARCH_ROWS = 25  # nhentai: one search page per seed
RETRY_AFTER_S = 60  # the source message says "retry in a minute"
RANDOM_TERM = "language:english"  # the fixed broad term for Random on a web source
_GENERIC_SCOPES = ("language", "category")  # never a useful query word


class RecommendItem(BaseModel):
    id: str
    source: str
    title: str
    author: str = ""
    thumb_url: str = ""
    saveable: bool | None = None
    saved: SavedRef | None = None


class RecommendResponse(BaseModel):
    items: list[RecommendItem]


@dataclass
class Cand:
    """One candidate: what ranking needs, plus a payload the row builder reads."""

    key: str
    tags: set[str]
    people: set[str]
    payload: object
    score: float = 0.0
    same_author: bool = False
    extra: dict[str, object] = field(default_factory=dict)


def _fold(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").split())


def _people(*names: str) -> set[str]:
    return {_fold(n) for n in names if n.strip()}


def idf_table(seed: set[str], pool: list[Cand]) -> dict[str, float]:
    """`ln(1 + N / df)` per seed tag; N and df count the pool plus the seed."""
    n = len(pool) + 1
    out: dict[str, float] = {}
    for t in seed:
        df = 1 + sum(1 for c in pool if t in c.tags)
        out[t] = math.log(1 + n / df)
    return out


def rank(seed_tags: set[str], seed_people: set[str], pool: list[Cand]) -> list[Cand]:
    """Author or group matches first, then by idf score; rows under the floor are dropped.

    The floor is MIN_SCORE, lower for a seed whose total weight is small.

    An author match stays even when its tag score is low (a seed with no tags ranks by author).
    """
    idf = idf_table(seed_tags, pool)
    floor = min(MIN_SCORE, MIN_SHARE * sum(idf.values()))
    kept: list[Cand] = []
    for c in pool:
        c.score = sum(idf[t] for t in seed_tags & c.tags)
        c.same_author = bool(seed_people & c.people)
        if c.same_author or c.score >= floor:
            kept.append(c)
    kept.sort(key=lambda c: (not c.same_author, -c.score, c.key))
    return kept


def _passes(tags: dict[str, list[str]], rules: RuleSet, safe: bool, allow: bool) -> bool:
    """Reject rules and safe mode, as search rows are checked."""
    verdict = evaluate(tags, rules)
    if verdict is not None and verdict.decision != "warn":
        return False
    blur = Blur(tag=verdict.tag) if verdict else None
    return not is_hidden_in_safe_mode(blur, safe, allow)


# --- Stump ---


def _book_cand(b: BookDTO) -> Cand:
    artist, group = title_people(b.title)
    return Cand(
        key=b.id,
        tags={_fold(t) for t in b.tags},
        people=_people(artist, group, *b.authors),
        payload=b,
    )


def _stump_row(b: BookDTO) -> RecommendItem:
    return RecommendItem(
        id=b.id,
        source="stump",
        title=b.title,
        author=book_author(b),
        thumb_url=book_item(b).thumb_url,
    )


def _stump_walk(request: Request) -> list[BookDTO]:
    try:
        books = book_server_of(request.app).tagged_books("", [])
    except BookServerError as e:
        raise ApiError(e.status, e.code, e.message) from None
    # Stump lists a trashed book until its debounced scan ran, and a walk in that window is
    # cached for minutes: the trash records are the truth.
    trash = getattr(request.app.state, "trash", None)
    owned = trash.stump_owned_ids() if trash is not None else set()
    return [b for b in books if not b.deleted and b.id not in owned]


def _stump_seed(request: Request, id: str, kind: str) -> tuple[set[str], set[str], set[str]]:
    """(tags, people, ids to drop) of a book, or of a series with its own books' tags."""
    server = book_server_of(request.app)
    try:
        if kind == "series":
            series = server.get_series(id)
            books, _truncated = server.series_books(id)
            tags = {_fold(t) for t in series.tags} | {_fold(t) for b in books for t in b.tags}
            artist, group = title_people(series.title)
            return tags, _people(artist, group), {b.id for b in books}
        book = server.get_book(id)
    except BookServerError as e:
        raise ApiError(e.status, e.code, e.message) from None
    artist, group = title_people(book.title)
    return {_fold(t) for t in book.tags}, _people(artist, group, *book.authors), {book.id}


def _stump_rows(
    cands: list[Cand], rules: RuleSet, drop: set[str], safe: tuple[bool, bool]
) -> list[Cand]:
    return [
        c
        for c in cands
        if c.key not in drop
        and _passes({"": list(typing.cast(BookDTO, c.payload).tags)}, rules, *safe)
    ]


# --- web ---


def _post_people(p: Post) -> set[str]:
    artist, group = title_people(p.title)
    return _people(artist, group, *p.tags.get("artist", []), *p.tags.get("group", []))


def _post_author(p: Post) -> str:
    artist, group = title_people(p.title)
    names = [*p.tags.get("artist", []), *p.tags.get("group", [])]
    return (p.tags.get("artist") or [""])[0] or artist or group or (names[0] if names else "")


def _post_cand(p: Post) -> Cand:
    names = {_fold(n) for scope, ns in p.tags.items() if scope not in _GENERIC_SCOPES for n in ns}
    return Cand(key=p.post_id, tags=names, people=_post_people(p), payload=p)


def _seed_query(post: Post) -> list[str]:
    """The author or group term if the seed has one, else up to 2 tags (no language/category)."""
    for scope in ("artist", "group"):
        names = post.tags.get(scope)
        if names:
            return [f"{scope}:{names[0]}"]
    tags = [n for scope, ns in post.tags.items() if scope not in _GENERIC_SCOPES for n in ns]
    return [f"tag:{n}" for n in tags[:2]]


def _search_page(request: Request, src: Source, terms: list[str], page: int) -> list[Post]:
    """One cached search page through the source's own throttle. Never retries."""
    cache = _cache_of(request)
    ckey = (src.id, tuple(sorted(terms)), page, None, parse_order(""), tuple(parse_rating("")))
    try:
        result = cache.get(ckey)
        if result is None:
            result = src.search(terms, page, None, parse_order(""), parse_rating(""))
            cache.put(ckey, result)
    except SourceError as e:
        if e.code == "rate_limited":
            raise ApiError(429, "rate_limited", e.message, retry_after=RETRY_AFTER_S) from None
        raise ApiError(502, e.code, e.message) from None
    pages = getattr(result, "pages", None)
    if isinstance(pages, int):
        _known_pages(request)[(src.id, tuple(sorted(terms)))] = pages
    return list(result.posts)


def _known_pages(request: Request) -> dict[tuple, int]:
    state = request.app.state
    pages = getattr(state, "recommend_pages", None)
    if pages is None:
        pages = state.recommend_pages = {}
    return pages


def _web_source(request: Request, source: str) -> Source:
    src = request.app.state.sources.get(source)
    if src is None:
        raise ApiError(422, "invalid", f"Unknown source {source}", field="source")
    return src


def _web_rows(
    request: Request, source: str, posts: list[Post], rules: RuleSet
) -> list[RecommendItem]:
    src = _web_source(request, source)
    remember(request.app, posts, rules.version)
    saved = JobStore(request.app.state.settings.db_path).saved_refs(
        source, [p.post_id for p in posts], {p.post_id: p.md5 for p in posts if p.md5}
    )
    can_save = getattr(src, "target", "stash") in {"stash", "stump"}
    return [
        RecommendItem(
            id=p.post_id,
            source=source,
            title=p.title or "",
            author=_post_author(p),
            thumb_url=proxy_path(source, p.post_id, "thumb"),
            saveable=can_save,
            saved=saved.get(p.post_id),
        )
        for p in posts
    ]


# --- endpoints ---


def _limit_of(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


@router.get("/recommend")
def recommend(
    request: Request,
    source: str,
    id: str,
    kind: Literal["book", "series"] = "book",
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    safe: bool | None = None,
) -> RecommendResponse:
    """Items like the seed, best first; empty when nothing reaches MIN_SCORE."""
    n = _limit_of(limit)
    rules = load_rules(request.app.state.settings.db_path)
    flags = resolve_safe(request, safe)
    if source == "stump":
        tags, people, drop = _stump_seed(request, id, kind)
        pool = _stump_rows([_book_cand(b) for b in _stump_walk(request)], rules, drop, flags)
        top = rank(tags, people, pool)[:n]
        return RecommendResponse(items=[_stump_row(typing.cast(BookDTO, c.payload)) for c in top])
    src = _web_source(request, source)
    seed = _authorize(request, src, id)
    terms = _seed_query(seed)
    if not terms:
        return RecommendResponse(items=[])
    rows = [p for p in _search_page(request, src, terms, 1)[:SEARCH_ROWS] if p.post_id != id]
    pool = [_post_cand(p) for p in rows if _passes(p.tags, rules, *flags)]
    seed_cand = _post_cand(seed)
    top = rank(seed_cand.tags, seed_cand.people, pool)[:n]
    return RecommendResponse(
        items=_web_rows(request, source, [typing.cast(Post, c.payload) for c in top], rules)
    )


@router.get("/recommend/random")
def recommend_random(
    request: Request,
    source: str,
    limit: int = Query(5, ge=1),
    exclude: str = "",
    safe: bool | None = None,
) -> RecommendResponse:
    """Random items of the same source, through the same rules; each shuffle is a new call."""
    n = _limit_of(limit)
    rules = load_rules(request.app.state.settings.db_path)
    flags = resolve_safe(request, safe)
    if source == "stump":
        books = [b for b in _stump_walk(request) if b.id != exclude]
        random.shuffle(books)
        picked = [b for b in books if _passes({"": list(b.tags)}, rules, *flags)][:n]
        return RecommendResponse(items=[_stump_row(b) for b in picked])
    src = _web_source(request, source)
    terms = [RANDOM_TERM]
    known = _known_pages(request).get((src.id, tuple(sorted(terms))))
    page = random.randint(1, known) if known else 1
    last = _last_random(request)
    try:
        posts = _search_page(request, src, terms, page)
    except ApiError as e:
        if e.code == "rate_limited" and source in last:
            posts = last[source]  # the last random page, never a retry
        else:
            raise
    else:
        last[source] = posts
    posts = list(posts)
    random.shuffle(posts)
    shown = [p for p in posts if p.post_id != exclude and _passes(p.tags, rules, *flags)][:n]
    return RecommendResponse(items=_web_rows(request, source, shown, rules))


# --- fixture mode (also what the OpenAPI dump for the frontend types reads) ---

fixture_router = APIRouter(prefix="/api")


def _fixture_rows(source: str) -> list[dict]:
    from app.fixtures.store import store  # noqa: PLC0415

    return store.visible("books") if source == "stump" else []


def _fixture_item(raw: dict, source: str) -> RecommendItem:
    return RecommendItem(
        id=str(raw["id"]), source=source, title=raw["title"], thumb_url=raw["thumb_url"]
    )


@fixture_router.get("/recommend")
def recommend_fixture(
    source: str,
    id: str,
    kind: Literal["book", "series"] = "book",
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    safe: bool | None = None,
) -> RecommendResponse:
    """Fixture Recommendations: books that share tags with the seed."""
    rows = _fixture_rows(source)
    seed = next((r for r in rows if str(r["id"]) == id), None)
    if seed is None:
        return RecommendResponse(items=[])
    pool = [
        Cand(str(r["id"]), {_fold(t) for t in r["tags"]}, set(), r)
        for r in rows
        if str(r["id"]) != id
    ]
    top = rank({_fold(t) for t in seed["tags"]}, set(), pool)[: _limit_of(limit)]
    return RecommendResponse(
        items=[_fixture_item(typing.cast(dict, c.payload), source) for c in top]
    )


@fixture_router.get("/recommend/random")
def recommend_random_fixture(
    source: str,
    limit: int = Query(5, ge=1),
    exclude: str = "",
    safe: bool | None = None,
) -> RecommendResponse:
    """Fixture Random: shuffled books."""
    rows = [r for r in _fixture_rows(source) if str(r["id"]) != exclude]
    random.shuffle(rows)
    return RecommendResponse(items=[_fixture_item(r, source) for r in rows[: _limit_of(limit)]])


def _last_random(request: Request) -> dict[str, list[Post]]:
    state = request.app.state
    last = getattr(state, "recommend_last", None)
    if last is None:
        last = state.recommend_last = {}
    return last
