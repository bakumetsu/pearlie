"""Generate deterministic media fixtures (images, videos, comic books)."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMG_COUNT: int = 40
VIDEO_COUNT: int = 6
BOOK_COUNT: int = 5
ASPECTS: tuple[tuple[int, int], ...] = ((3, 2), (2, 3), (1, 1), (16, 9))
LONG_SIDE: int = 1920
THUMB_LONG: int = 320
VIDEO_W: int = 640
VIDEO_H: int = 360
VIDEO_FPS: int = 24
VIDEO_DURATION: int = 6
PAGE_W: int = 1024
PAGE_H: int = 1440
_FFMPEG: str = "ffmpeg"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_rgb(i: int, salt: int = 0) -> tuple[int, int, int]:
    """Deterministic RGB triple from index *i* and *salt* (no randomness)."""
    return (
        (i * 37 + 53 + salt * 17) % 256,
        (i * 73 + 11 + salt * 31) % 256,
        (i * 119 + 47 + salt * 59) % 256,
    )


def _aspect_dims(index: int) -> tuple[int, int]:
    """(width, height) cycling through ASPECTS; long side = LONG_SIDE."""
    rw, rh = ASPECTS[index % len(ASPECTS)]
    if rw >= rh:
        return LONG_SIDE, LONG_SIDE * rh // rw
    return LONG_SIDE * rw // rh, LONG_SIDE


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _gradient(
    w: int, h: int, c0: tuple[int, int, int], c1: tuple[int, int, int],
) -> Image.Image:
    """Vertical RGB gradient, built via a 1×256 strip for speed."""
    strip = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255.0
        strip.putpixel(
            (0, y),
            (
                int(c0[0] + (c1[0] - c0[0]) * t),
                int(c0[1] + (c1[1] - c0[1]) * t),
                int(c0[2] + (c1[2] - c0[2]) * t),
            ),
        )
    return strip.resize((w, h), Image.Resampling.BILINEAR)


def _draw_shape(
    draw: ImageDraw.ImageDraw,
    w: int, h: int, i: int, color: tuple[int, int, int],
) -> None:
    """Draw a simple outline shape (circle / rect / triangle) chosen by index."""
    kind = i % 3
    m = min(w, h) // 5
    cx, cy = w // 2, h // 2
    line_w = max(3, m // 32)
    if kind == 0:
        draw.ellipse([cx - m, cy - m, cx + m, cy + m], outline=color, width=line_w)
    elif kind == 1:
        draw.rectangle(
            [cx - m, cy - m // 2, cx + m, cy + m // 2], outline=color, width=line_w,
        )
    else:
        draw.polygon(
            [(cx, cy - m), (cx - m, cy + m // 2), (cx + m, cy + m // 2)],
            outline=color,
            width=line_w,
        )


def _label_centered(
    draw: ImageDraw.ImageDraw,
    w: int, h: int,
    text: str, font: ImageFont.ImageFont,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) / 2, (h - th) / 2), text, fill="white", font=font)


def _thumb_size(w: int, h: int) -> tuple[int, int]:
    """Size so the long side equals THUMB_LONG."""
    if w >= h:
        return THUMB_LONG, THUMB_LONG * h // w
    return THUMB_LONG * w // h, THUMB_LONG


def _skip(path: Path, force: bool) -> bool:
    """True when the target exists and we are not forced to overwrite."""
    return not force and path.exists()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def media_dir() -> Path:
    """Default fixture media directory."""
    return Path(__file__).parents[2] / "fixtures" / "media"


def ensure_media() -> None:
    """Generate fixtures into media_dir() if the directory is missing or empty."""
    d = media_dir()
    if d.exists() and any(d.iterdir()):
        return
    generate(d)


def read_cbz_page(cbz: Path, n: int) -> bytes:
    """Return the JPEG bytes of page *n* (1-based) from a CBZ, sorted by name."""
    with zipfile.ZipFile(cbz) as zf:
        pages = sorted(
            name for name in zf.namelist()
            if name.startswith("page_") and name.endswith(".jpg")
        )
        if n < 1 or n > len(pages):
            raise ValueError(f"page {n} out of range (1..{len(pages)})")
        return zf.read(pages[n - 1])


def _font_file() -> str | None:
    """Return the first existing font path formatted for an ffmpeg filter string."""
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for p in candidates:
        if p.exists():
            s = p.as_posix()
            # Escape the drive-letter colon for Windows ffmpeg filter syntax
            if len(s) >= 2 and s[1] == ":":
                s = s[0] + "\\" + s[1:]
            return s
    return None


def generate(out_dir: Path, *, force: bool = False) -> dict[str, bool]:
    """Generate all fixture media into *out_dir*.

    Returns ``{"videos": bool}`` where the value is False when ffmpeg is absent.
    """
    images_dir = out_dir / "images"
    videos_dir = out_dir / "videos"
    books_dir = out_dir / "books"
    images_dir.mkdir(parents=True, exist_ok=True)
    books_dir.mkdir(parents=True, exist_ok=True)

    # ── images ──────────────────────────────────────────────────────────────
    font_big = _font(256)
    for i in range(IMG_COUNT):
        path = images_dir / f"{i}.jpg"
        if _skip(path, force):
            continue
        w, h = _aspect_dims(i)
        c0, c1 = _seed_rgb(i), _seed_rgb(i, salt=1)
        img = _gradient(w, h, c0, c1)
        draw = ImageDraw.Draw(img)
        _draw_shape(draw, w, h, i, c1)
        _label_centered(draw, w, h, str(i), font_big)
        img.save(path, quality=85)

        # thumbnail
        tpath = images_dir / f"{i}_thumb.jpg"
        if not _skip(tpath, force):
            nw, nh = _thumb_size(w, h)
            img.resize((nw, nh), Image.Resampling.LANCZOS).save(tpath, quality=75)

    # ── videos ──────────────────────────────────────────────────────────────
    has_ffmpeg = shutil.which(_FFMPEG) is not None
    if not has_ffmpeg:
        print("ffmpeg not found: video fixtures skipped")
    else:
        videos_dir.mkdir(parents=True, exist_ok=True)
        for i in range(VIDEO_COUNT):
            mp4 = videos_dir / f"{i}.mp4"
            if not _skip(mp4, force):
                font = _font_file()
                if font is not None:
                    vf = (
                        f"drawtext=text='Video {i}':"
                        f"fontfile='{font}':"
                        f"fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2"
                    )
                else:
                    vf = "null"
                src = f"testsrc2=size={VIDEO_W}x{VIDEO_H}:rate={VIDEO_FPS}"
                subprocess.run(
                    [
                        _FFMPEG, "-y",
                        "-f", "lavfi", "-i", f"{src}:duration={VIDEO_DURATION}",
                        "-f", "lavfi", "-i", f"sine=frequency=440:duration={VIDEO_DURATION}",
                        "-vf", vf,
                        "-c:v", "libx264", "-preset", "fast",
                        "-c:a", "aac",
                        "-shortest",
                        "-movflags", "+faststart",
                        str(mp4),
                    ],
                    check=True, capture_output=True,
                )

            poster = videos_dir / f"{i}_poster.jpg"
            if not _skip(poster, force):
                subprocess.run(
                    [
                        _FFMPEG, "-y",
                        "-i", str(mp4),
                        "-frames:v", "1",
                        "-q:v", "2",
                        str(poster),
                    ],
                    check=True, capture_output=True,
                )

    # ── books ───────────────────────────────────────────────────────────────
    font_page = _font(128)
    for i in range(BOOK_COUNT):
        page_count = 8 + (i * 3) % 7  # deterministic: 8,11,14,10,13
        c0, c1 = _seed_rgb(i, salt=10), _seed_rgb(i, salt=20)

        pages: list[bytes] = []
        first_img: Image.Image | None = None
        for p in range(1, page_count + 1):
            pg = _gradient(PAGE_W, PAGE_H, c0, c1)
            d = ImageDraw.Draw(pg)
            _label_centered(d, PAGE_W, PAGE_H, f"{p:03d}", font_page)
            buf = io.BytesIO()
            pg.save(buf, format="JPEG", quality=85)
            pages.append(buf.getvalue())
            if p == 1:
                first_img = pg

        # CBZ archive
        cbz_path = books_dir / f"{i}.cbz"
        if not _skip(cbz_path, force):
            xml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                "<ComicInfo>\n"
                f"  <Title>Fixture Book {i}</Title>\n"
                f"  <Number>{i + 1}</Number>\n"
                f"  <PageCount>{page_count}</PageCount>\n"
                "</ComicInfo>\n"
            )
            with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in range(1, page_count + 1):
                    zf.writestr(f"page_{p:03d}.jpg", pages[p - 1])
                zf.writestr("ComicInfo.xml", xml)

        # book thumbnail (first page → 320 px long side)
        if first_img is not None:
            bpath = books_dir / f"{i}_thumb.jpg"
            if not _skip(bpath, force):
                nw, nh = _thumb_size(PAGE_W, PAGE_H)
                first_img.resize((nw, nh), Image.Resampling.LANCZOS).save(bpath, quality=75)

    return {"videos": has_ffmpeg}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else media_dir()
    result = generate(out)
    print(f"videos: {result['videos']}")


if __name__ == "__main__":
    _main()
