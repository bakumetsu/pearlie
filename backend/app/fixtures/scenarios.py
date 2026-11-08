from __future__ import annotations

import asyncio

from app.fixtures.store import store

NAMES = ("default", "empty", "errors", "conflict", "slow", "offline")


def set_scenario(name: str) -> None:
    """Set the active fixture scenario."""
    if name not in NAMES:
        raise ValueError(f"Unknown scenario: {name}")
    store.scenario = name


def active(name: str) -> bool:
    """Return True if the given scenario is active."""
    return store.scenario == name


async def slow_dependency() -> None:
    """Inject latency when the 'slow' scenario is active."""
    if active("slow"):
        await asyncio.sleep(1.5)
