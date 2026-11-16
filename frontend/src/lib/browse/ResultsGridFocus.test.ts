// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import type { Mode } from "./layout";
import { mockItems } from "./testFixtures";
import type { LibraryItem, WebItem } from "../api/client";

// D-31 card 4: focus pin, tab extension and revealed state. ResultsGrid renders only the window. jsdom has no layout, so width, viewport and
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


function wrapperAt(c: HTMLElement, index: number): HTMLElement | undefined {
  return cells(c).find((e) => e.getAttribute("aria-posinset") === String(index + 1));
}

function focusable(w: HTMLElement): HTMLElement {
  return w.querySelector<HTMLElement>("a, button")!;
}

describe("test 9: focus pin and tab extension", () => {
  const items = mockItems(3000, 11);
  it("a focused tile stays in the DOM when it leaves the window; blur removes it", async () => {
    const { container } = render(ResultsGrid, { ...props, items, mode: "grid" });
    await settle();
    const start = indices(container);
    const idx = start[2];
    focusable(wrapperAt(container, idx)!).focus();
    await scrollTo(60000);
    const far = indices(container);
    expect(far).toContain(idx);
    expect(far.indexOf(idx)).toBe(0 + far.filter((i) => i < idx).length);
    // The pinned tile keeps its item order in the DOM.
    expect(far).toEqual([...far].sort((a, b) => a - b));
    expect(far.length).toBeLessThanOrEqual(600);
    (document.activeElement as HTMLElement).blur();
    await scrollTo(60001);
    expect(indices(container)).not.toContain(idx);
  });

  it("while a tile has focus the window covers 12 items after and before it", async () => {
    const { container } = render(ResultsGrid, { ...props, items, mode: "grid" });
    await settle();
    const idx = indices(container)[0];
    focusable(wrapperAt(container, idx)!).focus();
    await scrollTo(90000);
    const got = indices(container);
    for (let k = 1; k <= 12; k++) expect(got).toContain(idx + k);
    for (let k = 1; k <= Math.min(12, idx); k++) expect(got).toContain(idx - k);
    for (const w of cells(container)) {
      expect(w.getAttribute("role")).toBe("listitem");
      expect(w.getAttribute("aria-setsize")).toBe("3000");
    }
  });

  it("focus moving to another tile moves the pin", async () => {
    const { container } = render(ResultsGrid, { ...props, items, mode: "grid" });
    await settle();
    const got0 = indices(container);
    const a = got0[0];
    const b = got0[got0.length - 1];
    focusable(wrapperAt(container, a)!).focus();
    focusable(wrapperAt(container, b)!).focus();
    await scrollTo(90000);
    const got = indices(container);
    expect(got).toContain(b);
    expect(got).not.toContain(a);
  });
});

describe("revealed state outlives the window", () => {
  it("reveal, scroll out, scroll back: still revealed", async () => {
    const items = mockItems(3000, 13).map((it, i) =>
      i === 0
        ? ({ kind: "image", id: "blurred", title: "b", thumb_url: "/t/b", favorite: false, added_at: "2026-01-01", width: 600, height: 800, blur: { tag: "nsfw" } } as unknown as Item)
        : it,
    );
    const { container } = render(ResultsGrid, { ...props, items, mode: "grid" });
    await settle();
    expect(container.querySelectorAll(".warn-overlay").length).toBe(1);
    const tile = wrapperAt(container, 0)!.querySelector<HTMLElement>(".media")!;
    tile.click();
    await tick();
    expect(container.querySelectorAll(".warn-overlay").length).toBe(0);
    await scrollTo(90000);
    expect(indices(container)).not.toContain(0);
    await scrollTo(0);
    expect(indices(container)).toContain(0);
    expect(container.querySelectorAll(".warn-overlay").length).toBe(0);
  });
});
