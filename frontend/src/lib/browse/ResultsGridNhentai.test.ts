// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import type { Mode } from "./layout";
import type { WebItem } from "../api/client";

// T-335: See all on nhentai showed "(25)" but no tiles. Web items without a size (width/height 0 or
// missing) must still lay out and render in every mode, measured width or not.

const WIDTH = 1000;
const VH = 800;

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("requestAnimationFrame", () => 0);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  Object.defineProperty(Element.prototype, "clientWidth", { configurable: true, get: () => WIDTH });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: VH });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return { top: 0 } as DOMRect;
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (Element.prototype as { clientWidth?: number }).clientWidth;
});

function nhentai(n: number, size: { width?: number; height?: number }): WebItem[] {
  return Array.from({ length: n }, (_u, i) => ({
    source: "nhentai",
    post_id: String(1000 + i),
    thumb_url: "/t/" + i,
    preview_url: "/p/" + i,
    media_kind: "image",
    title: "Book " + i,
    target: "stump",
    saveable: true,
    owned: false,
    ...size,
  })) as WebItem[];
}

const props = { zoom: 3, loading: false, skeletons: 12, saveStates: {}, onsave: () => {}, onnavigate: () => {} };

const SIZES: Array<[string, { width?: number; height?: number }]> = [
  ["zero size", { width: 0, height: 0 }],
  ["no size", {}],
  ["real size", { width: 350, height: 500 }],
];

describe("nhentai web items render tiles", () => {
  for (const mode of ["grid", "list", "wall", "masonry"] as Mode[]) {
    for (const [name, size] of SIZES) {
      it(`${mode}, ${name}`, async () => {
        const { container } = render(ResultsGrid, { ...props, mode, items: nhentai(25, size) });
        await tick();
        await new Promise((r) => setTimeout(r, 0));
        expect(container.querySelectorAll(".tile").length).toBeGreaterThan(0);
      });
    }
  }
});
