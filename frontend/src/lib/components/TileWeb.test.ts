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
});

describe("Search rows", () => {
  it("pins the nhentai row first and gives the video row landscape tiles", () => {
    expect(searchSrc).toContain('id === "nhentai"');
    expect(searchSrc).toContain('landscape={id === "stash_videos"}');
    expect(searchSrc).toContain('wide={id === "stash_videos"}');
  });
});
