"""The built wheel must carry every non-.py file under app/ (e.g. filters/base_list.txt)."""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).parents[1]


def test_wheel_contains_package_data(tmp_path: Path) -> None:
    pytest.importorskip("setuptools")
    proc = subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
            "--no-index", "-q", "-w", str(tmp_path), str(BACKEND_ROOT),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as zf:
        names = set(zf.namelist())

    assert "app/filters/base_list.txt" in names
    for f in (BACKEND_ROOT / "app").rglob("*"):
        if not f.is_file() or f.suffix in (".py", ".pyc") or "__pycache__" in f.parts:
            continue
        rel = f.relative_to(BACKEND_ROOT).as_posix()
        assert rel in names, f"missing {rel} in wheel"
