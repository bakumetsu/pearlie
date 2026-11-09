"""HLS segment upstream path mapping for the real Stash media proxy."""

from __future__ import annotations

from pathlib import Path

import httpx

from tests.test_media_stash_real import make_client, stream_response

_M3U8_REAL = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:3\n"
    "#EXTINF:2.0,\n"
    "stream.m3u8/0.ts?resolution=STANDARD&apikey=zzz\n"
    "#EXTINF:2.0,\n"
    "http://stash.test/scene/5/stream.m3u8/1.ts?resolution=STANDARD&apikey=zzz\n"
)


def test_hls_segment_upstream_path(tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.raw_path.decode())
        if request.url.path.endswith("stream.m3u8"):
            return stream_response(200, _M3U8_REAL.encode(), {})
        return stream_response(200, b"seg", {})

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/stash/videos/5/s/stream.m3u8")
    lines = r.text.splitlines()
    assert "0.ts?resolution=STANDARD" in lines
    assert "1.ts?resolution=STANDARD" in lines
    assert "apikey" not in r.text

    paths.clear()
    for line in (ln for ln in lines if ln.endswith("STANDARD")):
        assert client.get(f"/api/media/stash/videos/5/s/{line}").status_code == 200
    assert paths == [
        "/scene/5/stream.m3u8/0.ts?resolution=STANDARD",
        "/scene/5/stream.m3u8/1.ts?resolution=STANDARD",
    ]
