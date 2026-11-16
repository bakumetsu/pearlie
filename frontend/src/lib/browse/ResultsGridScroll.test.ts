// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import type { Mode } from "./layout";
import { keyOf } from "../stores/shared.svelte";
import { mockItems } from "./testFixtures";

// D-31 card 3, tests 7 and 8: scroll anchor, restore on return, resize keeps the anchor tile.
// jsdom has no layout, so width, viewport and scroll are mocked; rAF is queued and flushed by the test.

const VH = 800;
const MODES: Mode[] = ["wall", "masonry", "grid", "list"];

let width = 1000;
let scrollY = 0;
let rafQueue: Array<() => void> = [];
let roCallbacks: Array<() => void> = [];

beforeEach(() => {
  width = 1000;
  scrollY = 0;
  rafQueue = [];
  roCallbacks = [];
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        roCallbacks.push(cb);
      }
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("requestAnimationFrame", (cb: () => void) => rafQueue.push(cb));
  vi.stubGlobal("cancelAnimationFrame", () => {
    rafQueue = [];
  });
  Object.defineProperty(Element.prototype, "clientWidth", { configurable: true, get: () => width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: VH });
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => scrollY });
  window.scrollTo = ((_x: number, y: number) => {
    scrollY = y;
  }) as typeof window.scrollTo;
  window.scrollBy = ((_x: number, dy: number) => {
    scrollY += dy;
  }) as typeof window.scrollBy;
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return { top: this.classList.contains("rg") ? -scrollY : 0 } as DOMRect;
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

type Handle = {
  getAnchor(): { key: string; offset: number; sig: string } | null;
  getSig(): string;
  isReady(): boolean;
  scrollToKey(key: string, offset?: number): boolean;
};

async function settle() {
  await tick();
  await new Promise((r) => setTimeout(r, 0));
  await tick();
}

function flushRaf() {
  const q = rafQueue;
  rafQueue = [];
  q.forEach((f) => f());
}

// Screen y of a rendered tile's top (translate y minus the scroll), or null when it is not rendered.
function screenY(c: HTMLElement, key: string): number | null {
  const at = items.findIndex((it) => keyOf(it) === key);
  const cell = c.querySelector<HTMLElement>(`.vcell[aria-posinset="${at + 1}"]`);
  const m = cell ? /translate\([^,]+,\s*([\d.]+)px\)/.exec(cell.style.transform) : null;
  return m ? Number(m[1]) - scrollY : null;
}

const items = mockItems(2000, 11);

async function mount(mode: Mode, onready?: () => void) {
  const r = render(ResultsGrid, { ...props, items, mode, onready });
  await settle();
  return { ...r, handle: r.component as unknown as Handle };
}

describe("test 7: scroll restore", () => {
  for (const mode of MODES) {
    it(`${mode}: same width returns to the same first visible tile`, async () => {
      const a = await mount(mode);
      scrollY = 30000;
      flushRaf();
      await tick();
      const anchor = a.handle.getAnchor()!;
      expect(anchor).not.toBeNull();
      a.unmount();
      scrollY = 0;

      const onready = vi.fn();
      const b = await mount(mode, onready);
      expect(onready).toHaveBeenCalledTimes(1);
      expect(b.handle.isReady()).toBe(true);
      expect(b.handle.getSig()).toBe(anchor.sig);
      expect(b.handle.scrollToKey(anchor.key, anchor.offset)).toBe(true);
      const back = b.handle.getAnchor()!;
      expect(back.key).toBe(anchor.key);
      expect(back.offset).toBeCloseTo(anchor.offset, 3);
    });

    it(`${mode}: a different width keeps the anchor tile first`, async () => {
      const a = await mount(mode);
      scrollY = 30000;
      flushRaf();
      await tick();
      const anchor = a.handle.getAnchor()!;
      a.unmount();
      scrollY = 0;

      width = 600;
      const b = await mount(mode);
      expect(b.handle.getSig()).not.toBe(anchor.sig);
      b.handle.scrollToKey(anchor.key, anchor.offset);
      await settle();
      // Row-mates share a top, so check the anchor tile's place, not which tile is first.
      expect(screenY(b.container, anchor.key)).toBeCloseTo(-anchor.offset, 3);
    });
  }

  it("scrollToKey with no offset leaves an on-screen tile alone and reports an unknown key", async () => {
    const a = await mount("grid");
    const first = a.handle.getAnchor()!;
    a.handle.scrollToKey(first.key);
    expect(scrollY).toBe(0);
    expect(a.handle.scrollToKey("nope:0")).toBe(false);
  });
});

describe("test 8: resize keeps the anchor tile", () => {
  for (const mode of MODES) {
    it(mode, async () => {
      const a = await mount(mode);
      scrollY = 30000;
      flushRaf();
      await tick();
      const before = a.handle.getAnchor()!;

      width = 700;
      roCallbacks.forEach((cb) => cb());
      flushRaf();
      await settle();
      flushRaf();

      expect(a.handle.getAnchor()!.sig).not.toBe(before.sig);
      // List rows keep their height at any width, so only the other modes must move the scroll.
      if (mode !== "list") expect(scrollY).not.toBe(30000);
      expect(screenY(a.container, before.key)).toBeCloseTo(-before.offset, 3);
    });
  }

  it("a height-only resize (address bar) does not reset the layout", async () => {
    const a = await mount("grid");
    scrollY = 30000;
    flushRaf();
    await tick();
    const before = a.handle.getAnchor()!;
    const y = scrollY;
    window.dispatchEvent(new Event("resize"));
    roCallbacks.forEach((cb) => cb());
    flushRaf();
    await settle();
    expect(scrollY).toBe(y);
    expect(a.handle.getAnchor()).toEqual(before);
  });
});
