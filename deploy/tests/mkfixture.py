"""Library to build tarball fixtures for testing pearlie-update.sh."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path


def make_tarball(
    dest: Path,
    top: str,
    version: str,
    repo_root: Path,
    extra: list[tuple[str, str, str]] = (),
) -> None:
    omit_set: set[str] = set()
    file_extras: list[tuple[str, str]] = []
    symlink_extras: list[tuple[str, str]] = []

    for kind, name, data in extra:
        if kind == "omit":
            omit_set.add(name)
        elif kind == "file":
            file_extras.append((name, data))
        elif kind == "symlink":
            symlink_extras.append((name, data))

    pyproject_text = (
        "[project]\n"
        'name = "pearlie"\n'
        f'version = "{version}"\n'
    )

    base_entries: list[tuple[str, bytes]] = [
        ("backend/pyproject.toml", pyproject_text.encode()),
        ("deploy/pearlie-update.sh", (repo_root / "deploy" / "pearlie-update.sh").read_bytes()),
        ("deploy/requirements.lock", b"# lock\n"),
        ("frontend/package.json", b"{}"),
    ]

    dest.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(str(dest), "w:gz") as tf:
        for rel, content in base_entries:
            if rel in omit_set:
                continue
            info = tarfile.TarInfo(name=f"{top}/{rel}")
            info.size = len(content)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(content))

        for name, data in file_extras:
            content = data.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(content))

        for name, target in symlink_extras:
            info = tarfile.TarInfo(name=name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            info.mode = 0o755
            tf.addfile(info)
