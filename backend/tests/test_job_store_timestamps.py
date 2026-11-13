"""Job timestamps reach the API as explicit UTC, not naive SQLite text."""

from pathlib import Path

from app.db import init_db
from app.jobs.store import JobStore
from app.sources.base import Post


def test_job_timestamps_are_utc_iso(tmp_path: Path) -> None:
    path = tmp_path / "p.db"
    init_db(path)
    store = JobStore(path)
    post = Post(source="danbooru", post_id="1", md5="a" * 32, file_url="https://x/y.jpg")
    jid = store.enqueue(post, "stash", "t", "")
    job = store.get(jid)
    assert job is not None
    assert job.created_at.endswith("Z") and "T" in job.created_at
    assert job.finished_at is None
