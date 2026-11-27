"""Pure merge logic for the Discover merged row: rail sites, round robin, dedupe. No I/O."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

from app.sources.base import Post

PER_SITE = 12


def rail_sites(
    site_order: Iterable[str], hidden: Collection[str], available: Collection[str]
) -> list[str]:
    """Sites of the rail in rail order: not hidden and with a configured source."""
    return [s for s in site_order if s not in hidden and s in available]


def interleave[T](
    lists_by_site: Mapping[str, Sequence[T]],
    rail_order: Sequence[str],
    have: Collection[str] = (),
    per_site: int | None = PER_SITE,
) -> list[T]:
    """Round robin over the sites: item 1 of each site, then item 2 of each, and so on.

    Only the first *per_site* items of a site are used (None: the whole list). Sites in
    *have* make the first rounds; the other sites follow, so tiles the user already
    sees keep their place. A site that has no list is skipped; a short site drops out
    of later rounds. There is no cut on the total length.
    """
    known = [s for s in rail_order if s in lists_by_site]
    groups = [[s for s in known if s in have], [s for s in known if s not in have]]
    out: list[T] = []
    for group in groups:
        cut = {s: list(lists_by_site[s][:per_site]) for s in group}
        for i in range(max((len(v) for v in cut.values()), default=0)):
            out.extend(cut[s][i] for s in group if i < len(cut[s]))
    return out


def dedupe_key(post: Post) -> str:
    """The MD5 when the post has one, else source and post id."""
    return post.md5.lower() if post.md5 else f"{post.source}:{post.post_id}"


def dedupe(posts: Iterable[Post], key: Callable[[Post], str] = dedupe_key) -> list[Post]:
    """Drop later duplicates; the first post in row order wins and is not replaced."""
    seen: set[str] = set()
    out: list[Post] = []
    for p in posts:
        k = key(p)
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out
