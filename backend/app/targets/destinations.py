"""Destination management for Stash sites."""

import posixpath
from pathlib import Path

from app.db import connect


class DestinationError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def to_stash_path(path: str, prefix_pearlie: str = "", prefix_stash: str = "") -> str:
    """Map a Pearlie path to its Stash equivalent."""
    if not prefix_pearlie:
        return path
    if path == prefix_pearlie:
        return prefix_stash
    if path.startswith(prefix_pearlie + "/"):
        return prefix_stash + path[len(prefix_pearlie):]
    return path


def validate_folder(
    folder: str,
    library_paths: list[str],
    prefix_pearlie: str = "",
    prefix_stash: str = "",
) -> str:
    """Validate and normalize a destination folder path."""
    if ".." in folder.split("/"):
        raise DestinationError("invalid", "folder must not contain '..'", 422)
    normalized = posixpath.normpath(folder)
    if not posixpath.isabs(normalized):
        raise DestinationError("invalid", "folder must be an absolute path", 422)
    if prefix_pearlie and not (
        normalized == prefix_pearlie or normalized.startswith(prefix_pearlie + "/")
    ):
        raise DestinationError("outside_library", "folder is not inside a Stash library path", 400)
    mapped = to_stash_path(normalized, prefix_pearlie, prefix_stash)
    for lib in library_paths:
        lib_norm = posixpath.normpath(lib)
        if mapped == lib_norm or mapped.startswith(lib_norm + "/"):
            return normalized
    raise DestinationError("outside_library", "folder is not inside a Stash library path", 400)


def list_destinations(db_path: Path) -> list[dict[str, str]]:
    """Return all destinations ordered by site."""
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT site, folder FROM destinations ORDER BY site").fetchall()
        return [{"site": r["site"], "folder": r["folder"]} for r in rows]
    finally:
        conn.close()


def set_destination(db_path: Path, site: str, folder: str) -> None:
    """Insert or update a site's destination folder."""
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO destinations (site, folder) VALUES (?, ?) "
            "ON CONFLICT(site) DO UPDATE SET folder = excluded.folder",
            (site, folder),
        )
        conn.commit()
    finally:
        conn.close()


def delete_destination(db_path: Path, site: str) -> bool:
    """Delete a site's destination row; return True if a row was removed."""
    conn = connect(db_path)
    try:
        cur = conn.execute("DELETE FROM destinations WHERE site = ?", (site,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_default(db_path: Path, fallback: str) -> str:
    """Return the default folder, inserting the fallback if absent."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'default_folder'").fetchone()
        if row is not None:
            return row["value"]
        conn.execute("INSERT INTO settings (key, value) VALUES ('default_folder', ?)", (fallback,))
        conn.commit()
        return fallback
    finally:
        conn.close()


def set_default(db_path: Path, folder: str) -> None:
    """Upsert the default folder setting."""
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('default_folder', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (folder,),
        )
        conn.commit()
    finally:
        conn.close()


def resolve(db_path: Path, site: str, fallback_default: str) -> str:
    """Return the site's folder if set, else the default."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT folder FROM destinations WHERE site = ?", (site,)).fetchone()
        if row is not None:
            return row["folder"]
    finally:
        conn.close()
    return get_default(db_path, fallback_default)
