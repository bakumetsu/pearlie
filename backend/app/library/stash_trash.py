"""Stash side of the trash: read the entity, move its file, destroy the entry, restore."""

from __future__ import annotations

import errno
import json
import logging
import os
import time
import uuid
from pathlib import Path

from app.config import Settings
from app.db import connect
from app.library.trash import TrashError, TrashSpec, TrashStore
from app.models import LibraryItem
from app.targets import destinations
from app.targets.stash_client import StashClient, StashError
from app.targets.stash_library import image_item, video_item

logger = logging.getLogger("pearlie")

KIND_OF = {"images": "image", "videos": "video"}


def _files(dto: dict, kind: str) -> list[dict]:
    files = dto.get("visual_files" if kind == "image" else "files") or []
    return [f for f in files if f]


def _fingerprint(file: dict, name: str) -> str | None:
    for fp in file.get("fingerprints") or []:
        if fp.get("type") == name:
            return fp.get("value")
    return None


def _meta(dto: dict, kind: str, file: dict) -> dict:
    meta: dict = {
        "title": dto.get("title"),
        "rating100": dto.get("rating100"),
        "organized": dto.get("organized"),
        "date": dto.get("date"),
        "urls": dto.get("urls") or [],
        "tags": [t["name"] for t in dto.get("tags") or []],
        "performers": [p["name"] for p in dto.get("performers") or []],
        "studio": (dto.get("studio") or {}).get("name"),
        "md5": _fingerprint(file, "md5"),
        "oshash": _fingerprint(file, "oshash"),
        "stash_path": file.get("path"),
    }
    if kind == "image":
        meta["galleries"] = [
            {"id": g["id"], "title": g.get("title")} for g in dto.get("galleries") or []
        ]
    else:
        meta["details"] = dto.get("details")
        meta["markers"] = [
            {
                "title": m.get("title"),
                "seconds": m.get("seconds"),
                "primary_tag": (m.get("primary_tag") or {}).get("name"),
                "tags": [t["name"] for t in m.get("tags") or []],
            }
            for m in dto.get("scene_markers") or []
        ]
        meta["stash_ids"] = dto.get("stash_ids") or []
    return meta


class StashTrash:
    def __init__(self, settings: Settings, store: TrashStore, client: StashClient) -> None:
        self._s = settings
        self._store = store
        self._c = client

    def _mapping(self) -> tuple[str, str]:
        pp, ps, _ = destinations.get_mapping(
            self._s.db_path, self._s.stash_path_prefix_pearlie, self._s.stash_path_prefix_stash
        )
        return pp, ps

    def _to_local(self, stash_path: str) -> Path:
        pp, ps = self._mapping()
        return Path(destinations.to_pearlie_path(stash_path, pp, ps))

    def _to_stash(self, local: Path) -> str:
        pp, ps = self._mapping()
        return destinations.to_stash_path(local.as_posix(), pp, ps)

    def _check_under_library(self, local: Path) -> None:
        real = os.path.realpath(local)
        roots = [os.path.realpath(self._to_local(p)) for p in self._c.library_paths()]
        trash = os.path.realpath(self._store.dir)
        for root in roots:
            if trash == root or trash.startswith(root + os.sep):
                raise TrashError(503, "trash_unavailable", "Trash folder is inside a library")
        if not any(real == r or real.startswith(r + os.sep) for r in roots):
            raise TrashError(422, "path_outside_library", "Item is outside the library")

    def _probe(self, root: Path) -> str:
        """Rename a probe file from *root* into the trash folder and back; always clean up."""
        name = f".pearlie-probe-{uuid.uuid4().hex}"
        src = root / name
        dest = self._store.dir / name
        try:
            if not root.is_dir() or not os.access(root, os.W_OK):
                return "not_reachable"
            src.write_bytes(b"")
            try:
                os.rename(src, dest)
                os.rename(dest, src)
            except OSError as e:
                return "other_volume" if e.errno == errno.EXDEV else "not_reachable"
            return "ok"
        except OSError:
            return "not_reachable"
        finally:
            for p in (src, dest):
                try:
                    p.unlink()
                except OSError:
                    pass

    def probe_roots(self) -> list[dict]:
        """Per Stash library root: can a file move into the trash folder and back (cached 60 s)."""
        cached = getattr(self._store, "_probe_cache", None)
        if cached and time.monotonic() - cached[0] < 60:
            return cached[1]
        roots = []
        for i, stash_path in enumerate(self._c.library_paths()):
            state = self._probe(self._to_local(stash_path))
            roots.append({"index": i, "stash_path": stash_path, "state": state})
        self._store._probe_cache = (time.monotonic(), roots)  # type: ignore[attr-defined]
        return roots

    def delete(self, plural: str, id: str, group_id: str | None = None) -> dict:
        kind = KIND_OF[plural]
        self._store.check_dir()
        try:
            dto = self._c.get_trash_entity(kind, id)
            if dto is None:
                raise TrashError(404, "not_found", "Item not found")
            if self._store.active_for_entity("stash", id):
                raise TrashError(409, "already_trashed", "Item is already in the trash")
            files = _files(dto, kind)
            if len(files) != 1:
                raise TrashError(422, "multi_file", "Items with several files cannot be deleted")
            file = files[0]
            if file.get("zip_file"):
                raise TrashError(422, "in_archive", "Items inside an archive cannot be deleted")
            local = self._to_local(file["path"])
            self._check_under_library(local)
            md5 = _fingerprint(file, "md5")
            conn_row = self._saved_row(id)
            spec = TrashSpec(
                target="stash", kind=kind, entity_id=id,
                title=dto.get("title") or Path(file["path"]).name,
                orig_path=local, meta=_meta(dto, kind, file), md5=md5,
                source=conn_row[0], post_id=conn_row[1], group_id=group_id,
            )

            def destroy() -> None:
                self._c.destroy_item(kind, id)

            try:
                return self._store.delete(spec, destroy)
            except StashError:
                raise TrashError(502, "upstream_error", "Stash did not accept the delete") from None
        except StashError as e:
            raise TrashError(e.status, e.code, e.message) from None

    def _saved_row(self, id: str) -> tuple[str | None, str | None]:
        conn = connect(self._s.db_path)
        try:
            r = conn.execute(
                "SELECT source, post_id FROM saved_items WHERE target = 'stash' AND image_id = ?",
                (id,),
            ).fetchone()
        finally:
            conn.close()
        return (r["source"], r["post_id"]) if r else (None, None)

    def destroy_row(self, row: dict) -> None:
        """Start-up repair: drop the entry unless Stash already forgot it."""
        if self._c.get_trash_entity(row["kind"], row["entity_id"]) is not None:
            self._c.destroy_item(row["kind"], row["entity_id"])

    # -- restore ----------------------------------------------------------------

    def restore(self, token: str) -> LibraryItem:
        return self._store.restore(token, self._apply)

    def _wait_scan(self, job_id: str) -> None:
        deadline = time.monotonic() + self._s.stash_scan_timeout_s
        while True:
            status = self._c.find_job(job_id)["status"]
            if status in ("FINISHED", "UNKNOWN"):
                return
            if status in ("FAILED", "CANCELLED") or time.monotonic() >= deadline:
                raise RuntimeError("scan")
            time.sleep(0.5)

    def _apply(self, row: dict, new_path: Path) -> tuple[str, LibraryItem]:
        meta = json.loads(row["meta"] or "{}")
        kind = row["kind"]
        stash_path = self._to_stash(new_path)
        self._wait_scan(self._c.metadata_scan(stash_path))
        if kind == "image":
            new_id = self._c.find_image_by_path(stash_path)
            if new_id is None and meta.get("md5"):
                new_id = self._c.find_image_by_checksum(meta["md5"])
        else:
            new_id = self._c.find_scene_by_path(stash_path)
        if new_id is None:
            raise RuntimeError("not indexed")
        c = self._c
        fields: dict = {
            "title": meta.get("title"),
            "rating100": meta.get("rating100"),
            "organized": bool(meta.get("organized")),
            "date": meta.get("date"),
            "urls": meta.get("urls") or [],
            "tag_ids": c.resolve_tag_ids(meta.get("tags") or []),
            "performer_ids": [c.named_id("performer", n) for n in meta.get("performers") or []],
        }
        if meta.get("studio"):
            fields["studio_id"] = c.named_id("studio", meta["studio"])
        if kind == "image":
            fields["gallery_ids"] = [
                g["id"] for g in meta.get("galleries") or [] if c.gallery_exists(g["id"])
            ]
        else:
            fields["details"] = meta.get("details")
            fields["stash_ids"] = [
                {"endpoint": s["endpoint"], "stash_id": s["stash_id"]}
                for s in meta.get("stash_ids") or []
            ]
        fields = {k: v for k, v in fields.items() if v is not None}
        c.update_item("images" if kind == "image" else "videos", new_id, fields)
        if kind == "video":
            self._markers(new_id, meta.get("markers") or [])
        dto = c.get_image(new_id) if kind == "image" else c.get_scene(new_id)
        if dto is None:
            raise RuntimeError("gone")
        return new_id, (image_item(dto) if kind == "image" else video_item(dto))

    def _markers(self, scene_id: str, markers: list[dict]) -> None:
        for m in markers:
            try:
                tag_ids = self._c.resolve_tag_ids([m["primary_tag"]] + (m.get("tags") or []))
                self._c.marker_create(
                    {
                        "scene_id": scene_id,
                        "title": m.get("title") or "",
                        "seconds": m.get("seconds") or 0,
                        "primary_tag_id": tag_ids[0],
                        "tag_ids": tag_ids[1:],
                    }
                )
            except Exception:
                logger.warning("trash restore: marker skipped")
