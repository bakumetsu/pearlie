import type { LibraryItem, WebItem } from "../api/client";

// Shared by the layout and grid tests (D-31): deterministic, no network, no real server.

export function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randomAspects(n: number, seed = 1): number[] {
  const r = rng(seed);
  return Array.from({ length: n }, () => 0.5 + r() * 1.5);
}

// A mixed set: library images, videos and series, booru and nhentai posts; every 7th web item has a title.
export function mockItems(n: number, seed = 1): (LibraryItem | WebItem)[] {
  const r = rng(seed);
  return Array.from({ length: n }, (_u, i) => {
    const pick = Math.floor(r() * 4);
    if (pick === 0) {
      return {
        kind: "image",
        id: String(i),
        title: "image " + i,
        thumb_url: "/t/" + i,
        favorite: false,
        added_at: "2026-01-01",
        width: 400 + Math.floor(r() * 800),
        height: 400 + Math.floor(r() * 800),
      } as LibraryItem;
    }
    if (pick === 1) {
      return { kind: "video", id: String(i), title: "video " + i, thumb_url: "/t/" + i, favorite: false, added_at: "2026-01-01" } as LibraryItem;
    }
    return {
      source: pick === 2 ? "danbooru" : "nhentai",
      post_id: String(i),
      thumb_url: "/t/" + i,
      preview_url: "/p/" + i,
      media_kind: "image",
      title: i % 7 === 0 ? "post " + i : null,
      width: 300 + Math.floor(r() * 900),
      height: 300 + Math.floor(r() * 900),
      target: "stash",
      saveable: true,
      owned: false,
    } as WebItem;
  });
}
