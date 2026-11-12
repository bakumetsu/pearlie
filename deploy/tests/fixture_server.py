"""ThreadingHTTPServer fixture for local testing of pearlie-update.sh."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _resolve_release_dir(root: Path) -> Path | None:
    p = root / "current"
    if os.path.islink(str(p)):
        resolved = Path(os.readlink(str(p)))
        if not resolved.is_absolute():
            resolved = root / resolved
        return resolved
    if p.is_file():
        text = p.read_text().strip()
        if not text:
            return None
        resolved = Path(text)
        if not resolved.is_absolute():
            resolved = root / resolved
        return resolved
    return None


def _build_handler(
    root: Path,
    fixtures: Path,
    state: Path,
) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/health":
                self._health()
            elif path.startswith("/gh/") or path.startswith("/dl/"):
                self._fixture(path)
            else:
                self._not_found()

        def _health(self) -> None:
            release_dir = _resolve_release_dir(root)
            if release_dir is None:
                self._down()
                return
            vfile = release_dir / "app" / "VERSION.json"
            if not vfile.is_file():
                self._down()
                return
            try:
                data = json.loads(vfile.read_text(encoding="utf-8"))
                version: str = data["version"]
            except (json.JSONDecodeError, KeyError, OSError):
                self._down()
                return

            if (state / "stopped").exists():
                self._down()
                return

            bad = state / "bad_versions"
            if bad.exists():
                lines = bad.read_text(encoding="utf-8").splitlines()
                if version in lines:
                    self._down()
                    return

            body = json.dumps({"status": "ok", "version": version}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _fixture(self, path: str) -> None:
            rel = path.lstrip("/")
            target = (fixtures / rel).resolve()
            fix_resolved = fixtures.resolve()
            if not target.is_relative_to(fix_resolved):
                self._not_found()
                return
            if not target.is_file():
                self._not_found()
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _down(self) -> None:
            body = json.dumps({"error": "down"}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _not_found(self) -> None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return _Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()

    handler_cls = _build_handler(args.root, args.fixtures, args.state)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)
    print("ready", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
