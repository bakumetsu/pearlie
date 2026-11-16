// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import { VirtualLayout } from "./virtualLayout";
import { zoomSize } from "./layout";
import type { Mode } from "./layout";
import { itemAspect, captionLines } from "./sources";
import { mockItems } from "./testFixtures";
import { slotsInUse } from "../gifSlots";
import type { LibraryItem, WebItem } from "../api/client";

// D-31 card 2: ResultsGrid renders only the window. jsdom has no layout, so width, viewport and
// scroll are mocked; `requestAnimationFrame` is queued and flushed by the test.

type Item = LibraryItem | WebItem;

const WIDTH = 1000;
const VH = 800;
const MODES: Mode[] = ["wall", "masonry", "grid", "list"];

let scrollY = 0;
let rafQueue: Array<() => void> = [];
const observed = new Set<Element>();
const listeners = new Map<string, number>();

class FakeIO {
  constructor(private cb: (e: Partial<IntersectionObserverEntry>[]) => void) {}
  observe(node: Element) {
    observed.add(node);
    this.cb([{ target: node, isIntersecting: true }]);
  }
  unobserve(node: Element) {
    observed.delete(node);
  }
  disconnect() {}
}

const images: FakeImage[] = [];
class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private url = "";
  get src() {
    return this.url;
  }
  set src(v: string) {
    this.url = v;
    if (v) queueMicrotask(() => this.onload?.());
  }
  constructor() {
    images.push(this);
  }
}

beforeEach(() => {
  scrollY = 0;
  rafQueue = [];
  observed.clear();
  listeners.clear();
  images.length = 0;
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal("IntersectionObserver", FakeIO);
  vi.stubGlobal("Image", FakeImage);
  vi.stubGlobal("requestAnimationFrame", (cb: () => void) => rafQueue.push(cb));
  vi.stubGlobal("cancelAnimationFrame", () => {
    rafQueue = [];
  });
  Object.defineProperty(Element.prototype, "clientWidth", { configurable: true, get: () => WIDTH });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: VH });
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => scrollY });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return { top: this.classList.contains("rg") ? -scrollY : 0 } as DOMRect;
  });
  const add = window.addEventListener.bind(window);
  const remove = window.removeEventListener.bind(window);
  vi.spyOn(window, "addEventListener").mockImplementation((t: string, ...rest: unknown[]) => {
    listeners.set(t, (listeners.get(t) ?? 0) + 1);
    return (add as (...a: unknown[]) => void)(t, ...rest);
  });
  vi.spyOn(window, "removeEventListener").mockImplementation((t: string, ...rest: unknown[]) => {
    listeners.set(t, (listeners.get(t) ?? 0) - 1);
    return (remove as (...a: unknown[]) => void)(t, ...rest);
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (Element.prototype as { clientWidth?: number }).clientWidth;
});

const props = {
  zoom: 3,
  loading: false,
  skeletons: 12,
  saveStates: {},
  onsave: () => {},
  onnavigate: () => {},
};

async function settle() {
  await tick();
  await new Promise((r) => setTimeout(r, 0));
}

async function scrollTo(y: number) {
  scrollY = y;
  window.dispatchEvent(new Event("scroll"));
  const q = rafQueue;
  rafQueue = [];
  q.forEach((f) => f());
  await tick();
}

function cells(c: HTMLElement): HTMLElement[] {
  return Array.from(c.querySelectorAll<HTMLElement>(".vcell"));
}

function indices(c: HTMLElement): number[] {
  return cells(c).map((e) => Number(e.getAttribute("aria-posinset")) - 1);
}

function totalOf(c: HTMLElement): number {
  return parseFloat(c.querySelector<HTMLElement>(".vwin")!.style.height);
}

function yOf(e: HTMLElement): number {
  return Number(/translate\([^,]+,\s*([\d.]+)px\)/.exec(e.style.transform)![1]);
}

function expected(mode: Mode, items: Item[], top: number): number[] {
  const l = new VirtualLayout();
  l.reset(mode, WIDTH, zoomSize(mode, 3), items.map(itemAspect), {
    lines: items.map((i) => (mode === "grid" || mode === "list" ? captionLines(i, mode) : 0)),
  });
  return l.range(top - 1.5 * VH, top + VH + 1.5 * VH).map((p) => p.index);
}

describe("test 5: only the window renders (5,000 items)", () => {
  const items = mockItems(5000, 7);
  for (const mode of MODES) {
    it(mode, async () => {
      const { container } = render(ResultsGrid, { ...props, items, mode });
      await settle();
      expect(container.querySelector("[role=list]")).not.toBeNull();
      const total = totalOf(container);
      for (const top of [0, total / 2, total - VH]) {
        await scrollTo(top);
        const got = indices(container);
        expect(got.length).toBeGreaterThan(0);
        expect(got.length).toBeLessThanOrEqual(600);
        expect(got).toEqual(expected(mode, items, top));
      }
    });
  }
});

describe("test 6: appending pages", () => {
  it("50 items 40 times: bounded DOM, flat layout cost, one reset", async () => {
    const all = mockItems(2050, 3);
    const touched: number[] = [];
    const orig = VirtualLayout.prototype.append;
    vi.spyOn(VirtualLayout.prototype, "append").mockImplementation(function (this: VirtualLayout, ...a: Parameters<VirtualLayout["append"]>) {
      orig.apply(this, a);
      touched.push(this.stats.touched);
    });
    const reset = vi.spyOn(VirtualLayout.prototype, "reset");
    const { container, rerender } = render(ResultsGrid, { ...props, items: all.slice(0, 50), mode: "wall" });
    await settle();
    for (let n = 100; n <= 2050; n += 50) {
      await rerender({ items: all.slice(0, n) });
      await tick();
      expect(cells(container).length).toBeLessThanOrEqual(600);
    }
    expect(reset).toHaveBeenCalledTimes(1);
    expect(touched).toHaveLength(40);
    expect(Math.max(...touched)).toBeLessThanOrEqual(70);
    expect(container.querySelectorAll("[aria-setsize='2050']").length).toBeGreaterThan(0);
  });
});

describe("test 10: links stay plain", () => {
  for (const mode of MODES) {
    it(mode + ": href and data-key present; ctrl and middle click are not prevented", async () => {
      const libs: Item[] = Array.from({ length: 30 }, (_u, i) => ({ kind: "image", id: String(i), title: "t" + i, thumb_url: "/t/" + i, favorite: false, added_at: "x", width: 100, height: 100 }) as LibraryItem);
      const webs: Item[] = Array.from({ length: 10 }, (_u, i) => ({ source: "danbooru", post_id: "p" + i, thumb_url: "/t/p" + i, preview_url: "/p/" + i, media_kind: "image", title: null, width: 100, height: 100, target: "stash", saveable: true, owned: false }) as WebItem);
      const onopenitem = vi.fn();
      const onopenweb = vi.fn();
      const { container } = render(ResultsGrid, { ...props, items: [...webs, ...libs], mode, onopenitem, onopenweb, webHref: (w: WebItem) => "/web/" + w.post_id });
      await settle();
      const libLinks = Array.from(container.querySelectorAll<HTMLAnchorElement>("a.tile"));
      const webLinks = Array.from(container.querySelectorAll<HTMLAnchorElement>("a.open"));
      expect(libLinks.length).toBeGreaterThan(0);
      expect(webLinks.length).toBeGreaterThan(0);
      for (const a of [...libLinks, ...webLinks]) expect(a.getAttribute("href")).toBeTruthy();
      for (const a of libLinks) expect(a.getAttribute("data-key")).toMatch(/^image:/);
      for (const init of [{ ctrlKey: true }, { button: 1 }]) {
        for (const a of [libLinks[0], webLinks[0]]) {
          const ev = new MouseEvent("click", { bubbles: true, cancelable: true, ...init });
          a.dispatchEvent(ev);
          expect(ev.defaultPrevented).toBe(false);
        }
      }
      expect(onopenitem).not.toHaveBeenCalled();
      expect(onopenweb).not.toHaveBeenCalled();
    });
  }
});

describe("test 12: GIF slots follow the window", () => {
  it("a playing tile that leaves the window gives its slot back and clears its preload", async () => {
    const items = mockItems(3000, 5);
    for (let i = 0; i < 3; i++) {
      items[i] = { kind: "image", id: "g" + i, title: "g", thumb_url: "/t/g" + i, gif_url: "/g/" + i + ".gif", favorite: false, added_at: "x", width: 100, height: 100 } as LibraryItem;
    }
    const { container } = render(ResultsGrid, { ...props, items, mode: "wall" });
    await settle();
    expect(slotsInUse()).toBe(3);
    expect(images.filter((im) => im.src.endsWith(".gif"))).toHaveLength(3);
    await scrollTo(totalOf(container) - VH);
    await settle();
    expect(slotsInUse()).toBe(0);
    expect(images.filter((im) => im.src.endsWith(".gif"))).toHaveLength(0);
  });
});

describe("test 13: grid and list row height from data", () => {
  it("grid: a row with one captioned tile is taller; the next row is not", async () => {
    const img = (i: number) => ({ kind: "image", id: String(i), title: "t", thumb_url: "/t", favorite: false, added_at: "x", width: 100, height: 100 }) as LibraryItem;
    const items: Item[] = Array.from({ length: 15 }, (_u, i) => img(i));
    items[2] = { kind: "video", id: "v", title: "v", thumb_url: "/t", favorite: false, added_at: "x", width: 100, height: 100 } as LibraryItem;
    const { container } = render(ResultsGrid, { ...props, items, mode: "grid" });
    await settle();
    const ys = [...new Set(cells(container).map(yOf))].sort((a, b) => a - b);
    const cw = (WIDTH - 16 * 4) / 5;
    expect(ys[1] - ys[0]).toBeCloseTo(cw + 26 + 16, 3);
    expect(ys[2] - ys[1]).toBeCloseTo(cw + 16, 3);
  });

  it("list: a titled web row is taller than an untitled one", async () => {
    const web = (i: number, title: string | null) => ({ source: "danbooru", post_id: String(i), thumb_url: "/t", preview_url: "/p", media_kind: "image", title, width: 100, height: 100, target: "stash", saveable: true, owned: false }) as WebItem;
    const { container } = render(ResultsGrid, { ...props, zoom: 1, items: [web(1, "a title"), web(2, null), web(3, null)], mode: "list" });
    await settle();
    expect(cells(container).map((c) => c.style.height)).toEqual(["53px", "49px", "49px"]);
  });
});

describe("test 15: long scrolling leaks nothing (5,000 items)", () => {
  const items = mockItems(5000, 9);
  function snapshot(c: HTMLElement) {
    return { observed: observed.size, slots: slotsInUse(), scroll: listeners.get("scroll") ?? 0, resize: listeners.get("resize") ?? 0, cells: cells(c).length };
  }
  for (const mode of MODES) {
    it(mode, async () => {
      const { container, unmount } = render(ResultsGrid, { ...props, items, mode });
      await settle();
      const total = totalOf(container);
      const pass = async () => {
        for (const f of [0.25, 0.5, 0.75, 1, 0.5, 0]) await scrollTo(f === 1 ? total - VH : total * f);
      };
      await pass();
      const first = snapshot(container);
      expect(first.cells).toBeLessThanOrEqual(600);
      expect(first.observed).toBeGreaterThan(0);
      for (let n = 0; n < 19; n++) await pass();
      expect(snapshot(container)).toEqual(first);
      unmount();
      await settle();
      expect(observed.size).toBe(0);
      expect(slotsInUse()).toBe(0);
      expect(listeners.get("scroll") ?? 0).toBe(0);
      expect(listeners.get("resize") ?? 0).toBe(0);
      expect(cells(container)).toHaveLength(0);
    });
  }
}, 120000);
