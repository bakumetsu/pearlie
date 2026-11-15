// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import Tile from "./Tile.svelte";
import type { WebItem } from "../api/client";
import searchSrc from "../../routes/Search.svelte?raw";

afterEach(() => {
  cleanup();
});

const web = (over: Record<string, unknown> = {}) =>
  ({
    source: "danbooru", post_id: "1", thumb_url: "/t.jpg", preview_url: "/p.jpg",
    width: 800, height: 400, tags: [], target: "stash", saved: false, ...over,
  }) as unknown as WebItem;

describe("Tile web shapes and fallback", () => {
  it("nhentai cover is 2 / 3", () => {
    const { container } = render(Tile, { item: web({ source: "nhentai" }) });
    expect(container.querySelector<HTMLElement>(".media")!.style.aspectRatio).toBe("2 / 3");
  });

  it("booru post keeps its native aspect", () => {
    const { container } = render(Tile, { item: web() });
    expect(container.querySelector<HTMLElement>(".media")!.style.aspectRatio).toBe("800 / 400");
  });

  it("img error falls back to preview_url, then placeholder; Retry resets", async () => {
    const { container } = render(Tile, { item: web() });
    const img = () => container.querySelector("img")!;
    expect(img().getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(img().getAttribute("src")).toBe("/t.jpg");
    await fireEvent.error(img());
    expect(img().getAttribute("src")).toBe("/p.jpg");
    await fireEvent.error(img());
    expect(container.querySelector("img")).toBeNull();
    await fireEvent.click(container.querySelector<HTMLElement>(".retry")!);
    expect(img().getAttribute("src")).toBe("/t.jpg");
  });

  it("proxied thumb error goes to placeholder, never preview_url; Retry asks the proxy again", async () => {
    const proxied = "/api/media/web/danbooru/1/thumb";
    const { container } = render(Tile, {
      item: web({ thumb_url: proxied, preview_url: "/api/media/web/danbooru/1/preview" }),
    });
    const img = () => container.querySelector("img")!;
    expect(img().getAttribute("src")).toBe(proxied);
    await fireEvent.error(img());
    expect(container.querySelector("img")).toBeNull();
    await fireEvent.click(container.querySelector<HTMLElement>(".retry")!);
    expect(img().getAttribute("src")).toBe(proxied);
  });

  it("no thumb and no preview shows 'No preview' with no img and no Retry", () => {
    const { container, getByText } = render(Tile, { item: web({ thumb_url: "", preview_url: "" }) });
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".retry")).toBeNull();
    expect(getByText("No preview")).toBeTruthy();
  });
});

describe("Search rows", () => {
  it("does not pin a site row first, and gives the video row landscape tiles", () => {
    expect(searchSrc).not.toContain('id === "nhentai"');
    expect(searchSrc).toContain('landscape={id === "stash_videos"}');
    expect(searchSrc).toContain('wide={id === "stash_videos"}');
  });
});

describe("Tile grid cost", () => {
  it("web grid tile is content-visibility sized by its aspect and decodes async", () => {
    const { container } = render(Tile, { item: web(), variant: "grid" });
    const root = container.querySelector<HTMLElement>(".tile")!;
    expect(root.classList.contains("cv")).toBe(true);
    expect(root.style.aspectRatio).toBe("800 / 400");
    expect(container.querySelector("img")!.getAttribute("decoding")).toBe("async");
  });

  it("list tile is not content-visibility", () => {
    const { container } = render(Tile, { item: web(), variant: "list" });
    expect(container.querySelector(".tile")!.classList.contains("cv")).toBe(false);
  });

  it("library image tile decodes async", () => {
    const item = { kind: "image", id: "1", title: "T", thumb_url: "/t.jpg", added_at: "2025-01-01T00:00:00Z", favorite: false };
    const { container } = render(Tile, { item: item as never, href: "/x" });
    expect(container.querySelector("img")!.getAttribute("decoding")).toBe("async");
    expect(container.querySelector(".tile")!.classList.contains("cv")).toBe(true);
  });
});
