from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>app</html>")
    (static / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (static / "manifest.webmanifest").write_text('{"name": "Pearlie"}')
    (static / "secret.txt").write_text("secret")
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=static,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


def test_favicon_is_svg(tmp_path: Path) -> None:
    r = _client(tmp_path).get("/favicon.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")


def test_manifest_served(tmp_path: Path) -> None:
    r = _client(tmp_path).get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["name"] == "Pearlie"


def test_unknown_and_unlisted_paths_get_index(tmp_path: Path) -> None:
    c = _client(tmp_path)
    for path in ("/library", "/secret.txt", "/icon-192.png", "/..%2fsecret.txt"):
        r = c.get(path)
        assert r.status_code == 200
        assert r.text == "<html>app</html>"
