// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import type { WebItem } from "../api/client";

// T-355: measuring the first caption called ResizeObserver.unobserve(null), which a real browser
// rejects with a TypeError inside an effect. The stub below throws the same way.

const unobserve = vi.fn((n: unknown) => {
  if (!(n instanceof Element)) throw new TypeError("parameter 1 is not of type 'Element'");
});

beforeEach(() => {
  unobserve.mockClear();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve = unobserve; });
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("requestAnimationFrame", () => 0);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  Object.defineProperty(Element.prototype, "clientWidth", { configurable: true, get: () => 1000 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return { top: 0, height: 20 } as DOMRect;
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (Element.prototype as { clientWidth?: number }).clientWidth;
});

describe("ResultsGrid caption measure", () => {
  it("never unobserves a missing node when the first caption appears", async () => {
    const items = Array.from({ length: 5 }, (_u, i) => ({
      source: "nhentai", post_id: String(i), thumb_url: "/t/" + i, preview_url: "/p/" + i, media_kind: "image",
      title: "Book " + i, target: "stump", saveable: true, owned: false, width: 350, height: 500,
    })) as WebItem[];
    const r = render(ResultsGrid, { items, mode: "list", zoom: 3, loading: false, skeletons: 5, saveStates: {}, onsave: () => {}, onnavigate: () => {} });
    await tick();
    await tick();
    expect(r.container.querySelectorAll(".vcell").length).toBe(5);
    expect(unobserve).not.toHaveBeenCalledWith(null);
  });
});
