// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import type { Mode } from "./layout";
import type { WebItem } from "../api/client";

// T-354: nhentai See all showed the header and no tiles. When the layout is built but the window
// holds no cell (the container reads far above or below the screen), the grid falls back to the
// flow layout, so a page with rows is never blank.

let top = 0;

beforeEach(() => {
  top = 0;
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("requestAnimationFrame", () => 0);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  Object.defineProperty(Element.prototype, "clientWidth", { configurable: true, get: () => 1000 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return { top } as DOMRect;
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (Element.prototype as { clientWidth?: number }).clientWidth;
});

function nhentai(n: number): WebItem[] {
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
    width: 350,
    height: 500,
  })) as WebItem[];
}

const props = { zoom: 3, loading: false, skeletons: 12, saveStates: {}, onsave: () => {}, onnavigate: () => {} };

describe("grid with rows never draws nothing", () => {
  for (const mode of ["grid", "list", "wall", "masonry"] as Mode[]) {
    for (const [name, t] of [["far above", -1e7], ["far below", 1e7]] as const) {
      it(`${mode}, container ${name} the screen`, async () => {
        top = t;
        const { container } = render(ResultsGrid, { ...props, mode, items: nhentai(25) });
        await tick();
        await new Promise((r) => setTimeout(r, 0));
        expect(container.querySelectorAll(".tile").length).toBeGreaterThan(0);
      });
    }
  }
});
