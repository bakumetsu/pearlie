// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import Tile from "./Tile.svelte";
import type { LibraryItem, WebItem } from "../api/client";

const opts = vi.hoisted(() => ({ options: { values: null as unknown } }));
vi.mock("../stores/options.svelte", () => opts);

type IOCb = (entries: Array<{ target: Element; isIntersecting: boolean }>) => void;
let ioCb: IOCb;
const targets: Element[] = [];
const images: FakeImage[] = [];

class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  src = "";
  constructor() {
    images.push(this);
  }
}

function setVisible(isIntersecting: boolean) {
  ioCb(targets.map((target) => ({ target, isIntersecting })));
}

async function loadGif() {
  images[images.length - 1].onload?.();
  await tick();
}

const GIF = "/api/media/web/danbooru/1/preview";
const web = (over: Record<string, unknown> = {}) =>
  ({
    source: "danbooru", post_id: "1", thumb_url: "/t.jpg", preview_url: GIF, gif_url: GIF,
    width: 800, height: 400, tags: [], target: "stash", saved: false, ...over,
  }) as unknown as WebItem;
const lib = (over: Record<string, unknown> = {}) =>
  ({
    kind: "image", id: "5", title: "t", thumb_url: "/th.jpg", gif_url: "/api/media/stash/images/5/full",
    tags: [], favorite: false, added_at: "2024-01-01", ...over,
  }) as unknown as LibraryItem;

beforeEach(() => {
  images.length = 0;
  targets.length = 0;
  vi.stubGlobal("IntersectionObserver", class {
    constructor(cb: IOCb) {
      ioCb = cb;
    }
    observe(el: Element) {
      targets.push(el);
    }
    unobserve() {}
  });
  vi.stubGlobal("Image", FakeImage);
  opts.options.values = { gif_grid: true } as never;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  opts.options.values = null as never;
});

const src = (c: HTMLElement) => c.querySelector("img")!.getAttribute("src");

describe("Tile grid GIF play", () => {
  it("web tile: still until in view and loaded, GIF while on screen, still again off screen", async () => {
    const { container } = render(Tile, { item: web() });
    expect(src(container)).toBe("/t.jpg");
    setVisible(true);
    await tick();
    expect(images[0].src).toBe(GIF);
    expect(src(container)).toBe("/t.jpg");
    await loadGif();
    expect(src(container)).toBe(GIF);
    setVisible(false);
    await tick();
    expect(src(container)).toBe("/t.jpg");
    expect(images[0].src).toBe("");
  });

  it("leaving before the load ends cancels it: no late swap", async () => {
    const { container } = render(Tile, { item: web() });
    setVisible(true);
    await tick();
    setVisible(false);
    await tick();
    expect(images[0].onload).toBeNull();
    expect(src(container)).toBe("/t.jpg");
  });

  it("library image tile plays the Stash GIF", async () => {
    const { container } = render(Tile, { item: lib() });
    setVisible(true);
    await tick();
    await loadGif();
    expect(src(container)).toBe("/api/media/stash/images/5/full");
  });

  it("no gif_url: never loads a GIF", async () => {
    const { container } = render(Tile, { item: web({ gif_url: null }) });
    setVisible(true);
    await tick();
    expect(images.length).toBe(0);
    expect(src(container)).toBe("/t.jpg");
  });

  it("setting off: stays still", async () => {
    opts.options.values = { gif_grid: false } as never;
    const { container } = render(Tile, { item: web() });
    setVisible(true);
    await tick();
    expect(images.length).toBe(0);
    expect(src(container)).toBe("/t.jpg");
  });

  it("reduced motion: stays still", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    const { container } = render(Tile, { item: web() });
    setVisible(true);
    await tick();
    expect(images.length).toBe(0);
    expect(src(container)).toBe("/t.jpg");
  });

  it("blurred tile does not load the GIF", async () => {
    const { container } = render(Tile, { item: web({ blur: { tag: "x" } }) });
    setVisible(true);
    await tick();
    expect(images.length).toBe(0);
    expect(container.querySelector("img")!.classList.contains("blur-img")).toBe(true);
  });

  it("GIF load error keeps the still", async () => {
    const { container } = render(Tile, { item: web() });
    setVisible(true);
    await tick();
    images[0].onerror?.();
    await tick();
    expect(src(container)).toBe("/t.jpg");
  });

  it("at most 6 GIFs play at once; the oldest goes back to still", async () => {
    const views = Array.from({ length: 7 }, (_, i) => {
      const r = render(Tile, { item: web({ post_id: String(i) }) });
      return r.container;
    });
    for (const [i, c] of views.entries()) {
      const target = targets.find((t) => c.contains(t))!;
      ioCb([{ target, isIntersecting: true }]);
      await tick();
      images[i].onload?.();
      await tick();
    }
    expect(src(views[0])).toBe("/t.jpg");
    expect(src(views[6])).toBe(GIF);
    expect(views.filter((c) => src(c) === GIF).length).toBe(6);
  });
});
