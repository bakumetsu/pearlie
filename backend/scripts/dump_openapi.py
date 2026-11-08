"""Dump the fixture-mode OpenAPI schema to a JSON file.

Usage (from backend/):  python -m scripts.dump_openapi <output.json>
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.config import Settings
from app.main import create_app


def main() -> None:
    out_path = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            mode="fixture",
            db_path=Path(tmp) / "p.db",
            static_dir=Path(tmp) / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
        app = create_app(settings)
        spec = app.openapi()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(spec, indent=2, sort_keys=False) + "\n")


if __name__ == "__main__":
    main()
