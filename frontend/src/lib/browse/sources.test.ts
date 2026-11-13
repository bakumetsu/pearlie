import { describe, it, expect } from "vitest";
import { isWebSource, itemKind, itemAspect } from "./sources";
import type { LibraryItem, WebItem } from "../api/client";

function lib(id: string, extra: object = {}): LibraryItem {
  return {
    kind: "image",
    id,
    title: id,
    thumb_url: "/t/" + id,
    favorite: false,
    added_at: "2026-01-01",
    ...extra,
  } as LibraryItem;
}

function web(id: string): WebItem {
  return { source: "danbooru", post_id: id, thumb_url: "/t/" + id, preview_url: "/p/" + id, media_kind: "image", title: null, width: 100, height: 100, target: "stash", saveable: true };
}

describe("isWebSource", () => {
  it("true for danbooru", () => {
    expect(isWebSource("danbooru")).toBe(true);
  });

  it("true for nhentai", () => {
    expect(isWebSource("nhentai")).toBe(true);
  });

  it("false for stash_images", () => {
    expect(isWebSource("stash_images")).toBe(false);
  });
});

describe("itemKind", () => {
  it("returns undefined for a web item", () => {
    expect(itemKind(web("1"))).toBeUndefined();
  });

  it("returns 'video' for a video library item", () => {
    const item = lib("v1", { kind: "video" });
    expect(itemKind(item)).toBe("video");
  });
});

describe("itemAspect", () => {
  it("returns width/height when both given (1600x800 -> 2)", () => {
    const item = lib("a1", { width: 1600, height: 800 });
    expect(itemAspect(item)).toBe(2);
  });

  it("returns 16/9 for a video without size", () => {
    const item = lib("a2", { kind: "video" });
    expect(itemAspect(item)).toBeCloseTo(16 / 9);
  });

  it("returns 2/3 for an image without size", () => {
    const item = lib("a3");
    expect(itemAspect(item)).toBeCloseTo(2 / 3);
  });

  it("returns 1 for a web item", () => {
    expect(itemAspect(web("1"))).toBe(1);
  });
});
