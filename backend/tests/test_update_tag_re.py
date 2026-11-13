import pytest

from app.update import repo


@pytest.mark.parametrize("tag", ["v1.2.3\n", "v1.2.3\n\n", "\nv1.2.3"])
def test_tag_with_newline_is_rejected(tag: str) -> None:
    assert repo.TAG_RE.match(tag) is None
    with pytest.raises(ValueError):
        repo.tag_download_url(tag)
    with pytest.raises(ValueError):
        repo.release_page_url(tag)


def test_sha_with_newline_is_rejected() -> None:
    with pytest.raises(ValueError):
        repo.sha_download_url("a" * 40 + "\n")


def test_plain_tag_still_valid() -> None:
    assert repo.TAG_RE.match("v0.12.3") is not None
