"""API routes reach Stash and Stump only through app.targets.servers."""

import ast
from pathlib import Path

from app.bookserver.base import BookDTO
from app.targets import servers

API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"
CONCRETE = (
    "app.targets.stash",
    "app.targets.stump",
    "app.library.stash_trash",
    "app.library.stump_trash",
)


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
    return names


def test_api_modules_skip_concrete_adapters() -> None:
    bad = {p.name: [n for n in _imports(p) if n.startswith(CONCRETE)] for p in API_DIR.glob("*.py")}
    assert {k: v for k, v in bad.items() if v} == {}


def test_book_matches_wraps_the_adapter_rule() -> None:
    book = BookDTO(
        id="b1",
        library_id="l",
        series_id="s",
        name="n",
        title="t",
        path="/lib/Some Title [123].cbz",
        created_at="2026-01-01",
    )
    assert servers.book_matches(book, "123") is True
    assert servers.book_matches(book, "999") is False
