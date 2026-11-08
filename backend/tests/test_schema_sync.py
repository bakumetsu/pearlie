"""Guard that frontend schema.gen.ts is in sync with the current OpenAPI schema."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO: Path = Path(__file__).parents[2]
COMMITTED: Path = REPO / "frontend" / "src" / "lib" / "api" / "schema.gen.ts"


def _openapi_typescript_bin() -> Path | None:
    """Return the openapi-typescript binary path, or None if not installed."""
    bin_dir = REPO / "frontend" / "node_modules" / ".bin"
    if sys.platform == "win32":
        p = bin_dir / "openapi-typescript.cmd"
    else:
        p = bin_dir / "openapi-typescript"
    return p if p.exists() else None


def test_schema_sync(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    ts_bin = _openapi_typescript_bin()
    if ts_bin is None:
        pytest.skip("openapi-typescript not installed in frontend/")

    openapi_json = tmp_path / "openapi.json"
    out_ts = tmp_path / "schema.gen.ts"

    # 1) Generate OpenAPI JSON via our script (cwd = backend/)
    subprocess.run(
        [sys.executable, "-m", "scripts.dump_openapi", str(openapi_json)],
        cwd=REPO / "backend",
        check=True,
    )

    # 2) Generate TS types from the JSON (cwd = frontend/)
    subprocess.run(
        [str(ts_bin), str(openapi_json), "-o", str(out_ts)],
        cwd=REPO / "frontend",
        check=True,
    )

    generated = out_ts.read_text(encoding="utf-8").replace("\r\n", "\n")
    committed = COMMITTED.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert generated == committed, "schema.gen.ts is stale: run `npm run gen:api` in frontend/"
