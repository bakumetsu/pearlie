// @vitest-environment jsdom
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from "vitest";

// T-335: nhentai See all showed "(25)" and no tiles. Mocked /api/search, no real site.
function post(i: number, size: { width?: number; height?: number }) {
  return {
    source: "nhentai",
    post_id: String(1000 + i),
    thumb_url: `/t/${i}`,
    preview_url: `/p/${i}`,
    media_kind: "image",
    title: `Book ${i}`,
    tags: [],
    target: "komga",
    saveable: true,
    owned: false,
    ...size,
  };
}

describe("SeeAll nhentai", () => {
  let infinite: boolean;
  let size: { width?: number; height?: number };
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
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/see-all?source=nhentai");
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      const json = (body: unknown, status = 200) =>
        Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
      if (url.pathname === "/api/options") {
        return json({ sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, source_pace: {}, infinite_scroll: infinite });
      }
      if (url.pathname === "/api/search") {
        return json({
          q: "",
          sections: [
            { id: "nhentai", title: "nhentai", items: Array.from({ length: 25 }, (_u, i) => post(i, size)), total: 25, next_page: null, pages: 1, page_size: 60, hidden: 0 },
          ],
        });
      }
      return json({}, 404);
    });
  });

  afterEach(() => {
    tl?.cleanup();
    vi.unstubAllGlobals();
  });

  for (const inf of [false, true]) {
    for (const [name, sz] of [["real size", { width: 350, height: 500 }], ["zero size", { width: 0, height: 0 }]] as const) {
      it(`shows 25 tiles (${inf ? "infinite" : "paged"}, ${name})`, async () => {
        infinite = inf;
        size = sz;
        tl = await import("@testing-library/svelte");
        const { default: App } = await import("../App.svelte");
        const r = tl.render(App);
        await vi.waitFor(() => expect(r.container.querySelectorAll(".tile").length).toBe(25));
      });
    }
  }
});
