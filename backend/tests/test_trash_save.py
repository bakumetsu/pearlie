"""A post whose file sits in the Pearlie trash is not saved again."""

from pathlib import Path

from app.library.trash import TrashSpec
from tests.test_jobs_real import make_client


def trash_post(tmp_path: Path, client, md5: str | None = None) -> str:
    lib = tmp_path / "lib"
    lib.mkdir()
    f = lib / "a.jpg"
    f.write_bytes(b"x")
    spec = TrashSpec(
        target="stash", kind="image", entity_id="7", title="a", orig_path=f,
        source="danbooru", post_id="1", md5=md5,
    )
    return client.app.state.trash.delete(spec, lambda: None)["token"]


def make(tmp_path):
    (tmp_path / "trash").mkdir()
    return make_client(tmp_path, trash_dir=tmp_path / "trash")


def test_save_of_trashed_post_is_409_in_trash_with_token(tmp_path):
    client, _, _ = make(tmp_path)
    token = trash_post(tmp_path, client)
    r = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "in_trash"
    assert body["token"] == token
    assert body["in_trash"] is True
    assert client.get("/api/jobs").json()["items"] == []


def test_other_post_still_saves(tmp_path):
    client, _, _ = make(tmp_path)
    trash_post(tmp_path, client)
    assert client.post("/api/save", json={"source": "danbooru", "post_id": "2"}).status_code == 202


def test_worker_dedupe_skips_trashed_post_by_post_id_and_md5(tmp_path):
    client, _, _ = make(tmp_path)
    trash_post(tmp_path, client, md5="AB" * 16)
    target = client.app.state.stash_target
    assert target._dedupe("danbooru", "1", None) == ("7", "in trash")
    assert target._dedupe("danbooru", "other", "ab" * 16) == ("7", "in trash")
