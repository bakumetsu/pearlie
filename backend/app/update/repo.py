"""URL builders for Pearlie GitHub repository endpoints."""

import re

API_BASE = "https://api.github.com/repos/bakumetsu/pearlie"
RELEASES_URL = "https://github.com/bakumetsu/pearlie/releases"
DEV_TREE_URL = "https://github.com/bakumetsu/pearlie/tree/dev"

LATEST_RELEASE_URL = API_BASE + "/releases/latest"
TAGS_URL = API_BASE + "/tags"
DEV_HEAD_URL = API_BASE + "/commits/dev"

TAG_RE = re.compile(r"^v\d+\.\d+\.\d+\Z")
SHA_RE = re.compile(r"^[0-9a-f]{40}\Z")


def tag_download_url(tag: str) -> str:
    if TAG_RE.match(tag) is None:
        raise ValueError(f"invalid tag: {tag!r}")
    return "https://codeload.github.com/bakumetsu/pearlie/tar.gz/refs/tags/" + tag


def sha_download_url(sha: str) -> str:
    if SHA_RE.match(sha) is None:
        raise ValueError(f"invalid sha: {sha!r}")
    return "https://codeload.github.com/bakumetsu/pearlie/tar.gz/" + sha


def release_page_url(tag: str) -> str:
    if TAG_RE.match(tag) is None:
        raise ValueError(f"invalid tag: {tag!r}")
    return RELEASES_URL + "/tag/" + tag


def _check_ref(ref: str) -> None:
    if TAG_RE.match(ref) is None and SHA_RE.match(ref) is None and ref != "dev":
        raise ValueError(f"invalid ref: {ref!r}")


def compare_url(base: str, head: str) -> str:
    _check_ref(base)
    _check_ref(head)
    return f"{API_BASE}/compare/{base}...{head}"


def tag_commits_url(tag: str) -> str:
    if TAG_RE.match(tag) is None:
        raise ValueError(f"invalid tag: {tag!r}")
    return f"{API_BASE}/commits?sha={tag}&per_page=100"


def compare_page_url(base: str, head: str) -> str:
    _check_ref(base)
    _check_ref(head)
    return f"https://github.com/bakumetsu/pearlie/compare/{base}...{head}"
