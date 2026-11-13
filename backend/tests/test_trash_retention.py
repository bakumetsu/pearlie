"""Trash retention tests (fixture store, mocks only)."""

from app.fixtures.store import store


def test_purge_preview_counts_without_mutating(client):
    store.reset()
    r3 = client.delete("/api/library/images/3")
    token3 = r3.json()["token"]
    store.trash[token3]["trashed_at"] -= 3 * 86400
    store.trash[token3]["expires"] -= 3 * 86400

    r4 = client.delete("/api/library/images/4")
    token4 = r4.json()["token"]

    assert len(store.trash) == 2

    resp = client.get("/api/trash/purge-preview", params={"days": 1})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    resp = client.get("/api/trash/purge-preview", params={"days": 2})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    resp = client.get("/api/trash/purge-preview", params={"days": 7})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0

    # Preview must not mutate
    assert len(store.trash) == 2
    assert token3 in store.trash
    assert token4 in store.trash


def test_lowering_without_confirm_purges_nothing(client):
    store.reset()
    r3 = client.delete("/api/library/images/3")
    token3 = r3.json()["token"]
    store.trash[token3]["trashed_at"] -= 3 * 86400
    store.trash[token3]["expires"] -= 3 * 86400

    r4 = client.delete("/api/library/images/4")
    token4 = r4.json()["token"]

    resp = client.put("/api/options", json={"trash_retention_days": 2})
    assert resp.status_code == 200
    assert resp.json()["trash_retention_days"] == 2

    # No confirm: nothing dropped, nothing hidden, old entry still restorable
    assert token3 in store.trash and token4 in store.trash
    assert len(client.get("/api/trash").json()["items"]) == 2


def test_lowering_with_confirm_purges_old_items_idempotent(client):
    store.reset()
    r3 = client.delete("/api/library/images/3")
    token3 = r3.json()["token"]
    store.trash[token3]["trashed_at"] -= 3 * 86400
    store.trash[token3]["expires"] -= 3 * 86400

    r4 = client.delete("/api/library/images/4")
    token4 = r4.json()["token"]

    assert len(store.trash) == 2

    body = {"trash_retention_days": 2, "confirm_purge": True}
    resp = client.put("/api/options", json=body)
    assert resp.status_code == 200
    assert resp.json()["trash_retention_days"] == 2

    # Backdated item purged, fresh item survives
    assert len(store.trash) == 1
    assert token4 in store.trash
    assert token3 not in store.trash

    resp = client.get("/api/trash")
    assert resp.status_code == 200
    body_ = resp.json()
    assert body_["retention_days"] == 2
    assert len(body_["items"]) == 1

    # Second identical PUT is idempotent (no new purge, no error)
    resp = client.put("/api/options", json=body)
    assert resp.status_code == 200
    assert len(store.trash) == 1
    assert token4 in store.trash


def test_options_retention_follows_store_after_reset(client):
    """BUG 5: options and the trash store must never disagree about retention."""
    store.reset()
    client.put("/api/options", json={"trash_retention_days": 30})
    assert client.get("/api/options").json()["trash_retention_days"] == 30
    assert store.retention_days == 30
    store.reset()
    assert client.get("/api/options").json()["trash_retention_days"] == store.retention_days


def test_raising_purges_nothing(client):
    store.reset()
    r3 = client.delete("/api/library/images/3")
    token3 = r3.json()["token"]

    resp = client.put("/api/options", json={"trash_retention_days": 30})
    assert resp.status_code == 200
    assert resp.json()["trash_retention_days"] == 30

    assert len(store.trash) == 1
    assert token3 in store.trash

    resp = client.get("/api/trash")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retention_days"] == 30
    assert len(body["items"]) == 1


def test_delete_uses_stored_retention(client):
    store.reset()
    resp = client.put("/api/options", json={"trash_retention_days": 30})
    assert resp.status_code == 200

    r3 = client.delete("/api/library/images/3")
    assert r3.status_code == 200
    assert r3.json()["retention_days"] == 30


def test_retention_bounds(client):
    store.reset()

    resp = client.put("/api/options", json={"trash_retention_days": 0})
    assert resp.status_code == 422

    resp = client.put("/api/options", json={"trash_retention_days": 366})
    assert resp.status_code == 422

    resp = client.put("/api/options", json={"trash_retention_days": 1})
    assert resp.status_code == 200

    resp = client.put("/api/options", json={"trash_retention_days": 365})
    assert resp.status_code == 200

    resp = client.get("/api/trash/purge-preview", params={"days": 0})
    assert resp.status_code == 422

    resp = client.get("/api/trash/purge-preview", params={"days": 366})
    assert resp.status_code == 422

    resp = client.get("/api/trash/purge-preview")
    assert resp.status_code == 422


def test_reset_restores_default(client):
    store.reset()
    resp = client.put("/api/options", json={"trash_retention_days": 30})
    assert resp.status_code == 200

    store.reset()
    assert store.retention_days == 7
