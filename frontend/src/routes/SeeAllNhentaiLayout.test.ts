// @vitest-environment jsdom
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from "vitest";

// T-354: nhentai See all (25 per page, total 657900) drew nothing after T-335. Mocked /api/search,
// measured width (the virtual layout runs only when the grid has a width), every layout mode.
function post(i: number) {
  return {
    source: "nhentai",
    post_id: String(1000 + i),
    thumb_url: `/t/${i}`,
    preview_url: `/p/${i}`,
    media_kind: "image",
    title: `Book ${i}`,
    tags: [],
    target: "stump",
    saveable: true,
    owned: false,
    width: 350,
    height: 500,
  };
}

describe("SeeAll nhentai, measured width", () => {
  let infinite: boolean;
  let mode: string;
  let tl: typeof import("@testing-library/svelte");

  beforeAll(async () => {
    await import("@testing-library/svelte");
    await import("../App.svelte");
  }, 60_000);

  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(1000);
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return { top: 0, height: 0, left: 0, width: 0, bottom: 0, right: 0 } as DOMRect;
    });
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/see-all?source=nhentai");
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      const json = (body: unknown, status = 200) =>
        Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
      if (url.pathname === "/api/options") {
        return json({ sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, source_pace: {}, infinite_scroll: infinite });
      }
      if (url.pathname === "/api/view-settings") {
        return json({ sources: { nhentai: { mode, per_page: 25, zoom: 3, per_page_options: [25, 60], per_page_max: 200, modes: ["grid", "wall", "masonry", "list"] } } });
      }
      if (url.pathname === "/api/search") {
        return json({
          q: "",
          sections: [
            { id: "nhentai", title: "nhentai", items: Array.from({ length: 25 }, (_u, i) => post(i)), total: 657900, next_page: 2, pages: 26316, page_size: 25, hidden: 0 },
          ],
        });
      }
      return json({}, 404);
    });
  });

  afterEach(() => {
    tl?.cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  for (const inf of [false, true]) {
    for (const m of ["grid", "wall", "masonry", "list"]) {
      it(`draws the tiles (${inf ? "infinite" : "paged"}, ${m})`, async () => {
        infinite = inf;
        mode = m;
        tl = await import("@testing-library/svelte");
        const { default: App } = await import("../App.svelte");
        const r = tl.render(App);
        // The list rows are tall, so the window holds the first rows only.
        await vi.waitFor(() => expect(r.container.querySelectorAll(".tile").length).toBeGreaterThanOrEqual(m === "list" ? 10 : 25));
      });
    }
  }
});
