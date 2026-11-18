"""Stump side of the trash: the file move stays Pearlie's; Stump shows the item `MISSING`.

The flow is the Komga one (`KomgaTrash`) over the `BookServer` interface: a debounced scan makes
Stump mark the moved item `MISSING`, `cleanLibrary` runs only when every MISSING item is one
Pearlie trashed, and a restore scans, finds the item (same id or a new id at the path), remaps
the id and writes tags, metadata and read progress back.
"""

from __future__ import annotations

from pathlib import Path

from app.library.komga_trash import KomgaTrash
from app.targets import destinations


class StumpTrash(KomgaTrash):
    label = "Stump"

    def _to_local(self, komga_path: str) -> Path:
        s = self._s
        p = destinations.to_pearlie_path(
            komga_path.replace("\\", "/"), s.stump_path_prefix_pearlie, s.stump_path_prefix_stump
        )
        return Path(p)

    def _to_komga(self, local: Path) -> str:
        s = self._s
        return destinations.to_stash_path(
            local.as_posix(), s.stump_path_prefix_pearlie, s.stump_path_prefix_stump
        )
