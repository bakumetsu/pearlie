"""Fetch real public-domain/CC0/CC-BY sample media into the fixture directory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.fixtures import mediagen  # noqa: E402

THROTTLE_SECONDS = 1.0
REQUEST_TIMEOUT = 60
USER_AGENT = "PearlieFixtureFetch/0.1 (local dev)"
ALLOWED_HOSTS = {"commons.wikimedia.org", "upload.wikimedia.org"}
MAX_MEDIA_BYTES = 200 * 1024 * 1024
SOURCES_PATH = Path(__file__).resolve().parent / "sample_sources.json"
KINDS = ("photos", "videos", "comics")


def load_sources() -> dict[str, Any]:
    """Return the pinned sample source list."""
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def _validate_host(url: str) -> None:
    """Raise ValueError when the URL host is not in ALLOWED_HOSTS."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"disallowed host: {host}")


def _throttle() -> None:
    """Sleep until at least THROTTLE_SECONDS has elapsed since import."""
    time.sleep(THROTTLE_SECONDS)


def fetch_bytes(url: str) -> bytes:
    """Download *url* with retries, UA, host check, and throttling."""
    _validate_host(url)
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            _throttle()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(2.0 * attempt)
    raise last_exc  # type: ignore[misc]


def _photo_url(title: str, width: int) -> str:
    """Build a Special:FilePath URL for a Commons file title."""
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(title)}?width={width}"


def _resize_long(img: Image.Image, long_side: int) -> Image.Image:
    """Resize *img* so its long side is at most *long_side* pixels."""
    w, h = img.size
    scale = long_side / max(w, h)
    if scale >= 1:
        return img
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _center_crop_square(img: Image.Image) -> Image.Image:
    """Center-crop *img* to a 1:1 square."""
    w, h = img.size
    side = min(w, h)
    box = ((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2)
    return img.crop(box)


def _open_image(data: bytes) -> Image.Image:
    """Open and verify *data* as an image, returning an RGB copy."""
    Image.open(BytesIO(data)).verify()
    img = Image.open(BytesIO(data))
    return img.convert("RGB")


def save_photo(item: dict[str, Any], index: int, data: bytes, out: Path) -> tuple[Path, Path]:
    """Save one photo and its thumb; return (image, thumb) paths."""
    img = _open_image(data)
    if item.get("crop") == "square":
        img = _center_crop_square(img)
    img = _resize_long(img, 1920)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    path = img_dir / f"{index}.jpg"
    img.save(path, format="JPEG", quality=85)
    thumb = img.resize(mediagen._thumb_size(*img.size), Image.LANCZOS)
    thumb_path = img_dir / f"{index}_thumb.jpg"
    thumb.save(thumb_path, format="JPEG", quality=75)
    return path, thumb_path


def save_comic(item: dict[str, Any], index: int, out: Path) -> tuple[Path, Path, int, str]:
    """Build one CBZ, thumb, ComicInfo; return (cbz, thumb, pages, url)."""
    files: list[str] = item["files"]
    book_dir = out / "books"
    book_dir.mkdir(parents=True, exist_ok=True)
    cbz_path = book_dir / f"{index}.cbz"
    tmp_path = book_dir / f"{index}.cbz.tmp"
    first_img: Image.Image | None = None
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for page_no, title in enumerate(files, start=1):
            url = _photo_url(title, 1400)
            img = _resize_long(_open_image(fetch_bytes(url)), 1400)
            if first_img is None:
                first_img = img
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            zf.writestr(f"page_{page_no:03d}.jpg", buf.getvalue())
        info = (
            "<ComicInfo xmlns='http://viralpi.github.io/2014/comicinfo.xsd'>"
            f"<Title>{item['title']}</Title>"
            f"<Number>{index + 1}</Number>"
            f"<PageCount>{len(files)}</PageCount>"
            "</ComicInfo>"
        )
        zf.writestr("ComicInfo.xml", info)
    tmp_path.replace(cbz_path)
    thumb = first_img.resize(mediagen._thumb_size(*first_img.size), Image.LANCZOS)
    thumb_path = book_dir / f"{index}_thumb.jpg"
    thumb.save(thumb_path, format="JPEG", quality=75)
    return cbz_path, thumb_path, len(files), _photo_url(files[0], 1400)


def cut_clip(ff: str, item: dict[str, Any], index: int, out: Path) -> tuple[Path, Path]:
    """Cut one clip with ffmpeg and extract its poster; return paths."""
    _validate_host(item["url"])
    _throttle()
    video_dir = out / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    out_path = video_dir / f"{index}.mp4"
    tmp_path = video_dir / f"{index}.mp4.tmp"
    poster_path = video_dir / f"{index}_poster.jpg"
    cmd = [
        ff,
        "-y",
        "-ss",
        str(item["start"]),
        "-t",
        "30",
        "-i",
        item["url"],
        "-vf",
        "scale=-2:720",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(tmp_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    tmp_path.replace(out_path)
    poster_cmd = [
        ff,
        "-y",
        "-ss",
        str(item["start"]),
        "-i",
        item["url"],
        "-frames:v",
        "1",
        "-vf",
        "scale=-2:720",
        "-q:v",
        "2",
        str(poster_path),
    ]
    subprocess.run(poster_cmd, check=True, capture_output=True, timeout=600)
    return out_path, poster_path


def _load_manifest(out: Path) -> list[dict[str, Any]]:
    """Load existing manifest items, or [] when absent/invalid."""
    path = out / "manifest.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = data.get("items", [])
    return items if isinstance(items, list) else []


def write_manifest(out: Path, items: list[dict[str, Any]]) -> None:
    """Atomically write manifest.json."""
    path = out / "manifest.json"
    tmp_path = out / "manifest.json.tmp"
    tmp_path.write_text(json.dumps({"items": items}, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _dir_size(path: Path) -> int:
    """Total bytes in a directory tree."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _process_photo(item: dict[str, Any], index: int, out: Path) -> dict[str, Any] | None:
    """Download/save one photo; return manifest entry or None on failure."""
    url = _photo_url(item["title"], 1920)
    try:
        path, _thumb = save_photo(item, index, fetch_bytes(url), out)
    except Exception as exc:
        print(f"photo {index} failed: {exc}")
        return None
    return {
        "file": path.relative_to(out).as_posix(),
        "kind": "photo",
        "title": item["title"],
        "url": url,
        "license": item["license"],
        "author": item["author"],
    }


def _process_video(
    ff: str | None, item: dict[str, Any], index: int, out: Path
) -> dict[str, Any] | None:
    """Cut one video; return manifest entry or None on failure/skip."""
    if ff is None:
        return None
    try:
        path, _poster = cut_clip(ff, item, index, out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"video {index} failed: {exc}")
        return None
    return {
        "file": path.relative_to(out).as_posix(),
        "kind": "video",
        "title": item["title"],
        "url": item["url"],
        "license": item["license"],
        "author": item["author"],
    }


def _process_comic(item: dict[str, Any], index: int, out: Path) -> dict[str, Any] | None:
    """Build one comic; return manifest entry or None on failure."""
    try:
        path, _thumb, page_count, url = save_comic(item, index, out)
    except Exception as exc:
        print(f"comic {index} failed: {exc}")
        return None
    return {
        "file": path.relative_to(out).as_posix(),
        "kind": "comic",
        "title": item["title"],
        "url": url,
        "license": item["license"],
        "author": item["author"],
        "page_count": page_count,
        "page_urls": page_count,
    }


def _skip_existing(out: Path, file_rel: str, force: bool, manifest_files: set[str]) -> bool:
    """True when an already-fetched file exists and should be skipped."""
    return not force and file_rel in manifest_files and (out / file_rel).exists()


def _dry_run(out: Path, only: str | None) -> int:
    """Print what would be fetched without network or writes."""
    sources = load_sources()
    manifest_files = {
        str(item.get("file", "")) for item in _load_manifest(out) if isinstance(item, dict)
    }
    for kind in KINDS:
        if only and kind != only:
            continue
        for index, item in enumerate(sources.get(kind, [])):
            if kind == "photos":
                count = mediagen.IMG_COUNT
                file_rel = f"images/{index}.jpg"
            elif kind == "videos":
                count = mediagen.VIDEO_COUNT
                file_rel = f"videos/{index}.mp4"
            else:
                count = mediagen.BOOK_COUNT
                file_rel = f"books/{index}.cbz"
            if index >= count:
                continue
            action = "skip" if _skip_existing(out, file_rel, False, manifest_files) else "fetch"
            print(f"{action}: {file_rel} ({kind}/{index}) {item.get('title', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Fetch pinned samples over generated placeholders."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", choices=KINDS, default=None)
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args(argv)

    out = args.out or mediagen.media_dir()

    if args.dry_run:
        return _dry_run(out, args.only)

    mediagen.generate(out)
    sources = load_sources()
    manifest_items = _load_manifest(out)
    manifest_files = {
        str(item.get("file", "")) for item in manifest_items if isinstance(item, dict)
    }
    current_items = [
        item
        for item in manifest_items
        if isinstance(item, dict) and (out / str(item.get("file", ""))).exists()
    ]
    counts = {kind: {"downloaded": 0, "skipped": 0, "failed": 0} for kind in KINDS}
    ff = mediagen._ffmpeg()
    if ff is None:
        print("ffmpeg not available; skipping videos")

    for kind in KINDS:
        if args.only and kind != args.only:
            continue
        limit = (
            mediagen.IMG_COUNT
            if kind == "photos"
            else (mediagen.VIDEO_COUNT if kind == "videos" else mediagen.BOOK_COUNT)
        )
        for index, item in enumerate(sources.get(kind, [])):
            if index >= limit:
                continue
            if kind == "photos":
                file_rel = f"images/{index}.jpg"
            elif kind == "videos":
                file_rel = f"videos/{index}.mp4"
            else:
                file_rel = f"books/{index}.cbz"

            if _skip_existing(out, file_rel, args.force, manifest_files):
                counts[kind]["skipped"] += 1
                continue

            if kind == "photos":
                entry = _process_photo(item, index, out)
            elif kind == "videos":
                entry = _process_video(ff, item, index, out)
            else:
                entry = _process_comic(item, index, out)

            if entry is None:
                if kind == "videos" and ff is None:
                    counts[kind]["skipped"] += 1
                else:
                    counts[kind]["failed"] += 1
            else:
                counts[kind]["downloaded"] += 1
                current_items.append(entry)
                manifest_files.add(entry["file"])

    write_manifest(out, current_items)
    for kind in KINDS:
        c = counts[kind]
        print(f"{kind}: downloaded={c['downloaded']} skipped={c['skipped']} failed={c['failed']}")
    size = _dir_size(out)
    print(f"media_dir size: {size} bytes")
    if size > MAX_MEDIA_BYTES:
        print(f"warning: media_dir exceeds {MAX_MEDIA_BYTES} bytes")

    downloaded = sum(c["downloaded"] for c in counts.values())
    failed = sum(c["failed"] for c in counts.values())
    return 1 if downloaded == 0 and failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
