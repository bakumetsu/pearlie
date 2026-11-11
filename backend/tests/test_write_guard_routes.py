"""Tests that every mutating /api route refuses cross-site requests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app

MUTATING = ("POST", "PUT", "PATCH", "DELETE")


def _mutating_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Return (method, path) for each mutating /api route; {params} -> 'x'."""
    out: list[tuple[str, str]] = []
    paths: dict[str, dict[str, Any]] = app.openapi()["paths"]
    for path, ops in paths.items():
        if not path.startswith("/api/"):
            continue
        for method in MUTATING:
            if method.lower() in ops:
                out.append((method, re.sub(r"\{[^}]+\}", "x", path)))
    return out


@pytest.mark.no_default_origin
def test_every_mutating_route_refuses_foreign_origin(client: TestClient) -> None:
    routes = _mutating_routes(cast(FastAPI, client.app))
    assert routes, "no mutating /api routes found"
    assert ("POST", "/api/update/apply") in routes
    assert ("PUT", "/api/update/settings") in routes
    for method, path in routes:
        resp = client.request(method, path, json={}, headers={"Origin": "http://evil.example"})
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
        assert resp.json()["code"] == "forbidden"


@pytest.mark.no_default_origin
def test_every_mutating_route_refuses_missing_origin(settings: Settings) -> None:
    tc = TestClient(create_app(settings))
    routes = _mutating_routes(cast(FastAPI, tc.app))
    assert routes, "no mutating /api routes found"
    for method, path in routes:
        resp = tc.request(method, path, json={})
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
        assert resp.json()["code"] == "forbidden"


@pytest.mark.no_default_origin
def test_every_mutating_route_refuses_foreign_origin_real(
    settings: Settings, tmp_path: Path
) -> None:
    real = Settings(
        mode="real",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        stash_url="http://stash.invalid",
        stash_api_key=SecretStr("k"),
        komga_url="http://komga.invalid",
        komga_api_key=SecretStr("k"),
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    real_app = create_app(real)
    tc = TestClient(real_app)  # no with-block: skips lifespan, no background tasks
    routes = _mutating_routes(cast(FastAPI, tc.app))
    assert routes, "no mutating /api routes found"
    for method, path in routes:
        resp = tc.request(method, path, json={}, headers={"Origin": "http://evil.example"})
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
        assert resp.json()["code"] == "forbidden"


def test_guard_passes_with_correct_origin(client: TestClient) -> None:
    resp = client.request("POST", "/api/update/apply", json={})
    assert resp.status_code == 503, (
        f"expected 503 (fixture-mode no-backend), got {resp.status_code}: {resp.text}"
    )
