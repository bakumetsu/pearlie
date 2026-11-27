// @vitest-environment jsdom
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from "vitest";

// source=merged: the mixed list from /api/discover/merged/list, always infinite, tiles with the site letter. Mocked, no real site.
function post(source: string, i: number) {
  return {
    source,
    post_id: String(i),
    thumb_url: `/t/${source}/${i}`,
    preview_url: `/p/${source}/${i}`,
    media_kind: "image",
    title: `${source} ${i}`,
    tags: [],
    target: "stash",
    saveable: true,
    owned: false,
  };
}

type Entries = { isIntersecting: boolean }[];

describe("SeeAll merged", () => {
  let listPages: number[];
  let searchCalls: number;
  let infinite: boolean;
  let observers: { cb: (e: Entries) => void; live: boolean }[];
  let tl: typeof import("@testing-library/svelte");

  beforeAll(async () => {
    await import("@testing-library/svelte");
    await import("../App.svelte");
  }, 60_000);

  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    observers = [];
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        entry: { cb: (e: Entries) => void; live: boolean };
        constructor(cb: (e: Entries) => void) {
          this.entry = { cb, live: false };
          observers.push(this.entry);
        }
        observe() { this.entry.live = true; }
        disconnect() { this.entry.live = false; }
        unobserve() { this.entry.live = false; }
      },
    );
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/see-all?source=merged");
    listPages = [];
    searchCalls = 0;
    infinite = false;
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      const json = (body: unknown, status = 200) =>
        Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
      if (url.pathname === "/api/options") {
        return json({ sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, source_pace: {}, infinite_scroll: infinite });
      }
      if (url.pathname === "/api/discover/merged/list") {
        const p = Number(url.searchParams.get("page") ?? "1");
        listPages.push(p);
        return json({ page: p, next_page: p < 2 ? p + 1 : null, items: [post("danbooru", p * 10), post("gelbooru", p * 10 + 1)], sites: [] });
      }
      if (url.pathname === "/api/search") searchCalls++;
      return json({}, 404);
    });
  });

  afterEach(() => {
    tl?.cleanup();
    vi.unstubAllGlobals();
  });

  it("reads the merged list, is infinite even when the option is off, and shows the site letters", async () => {
    tl = await import("@testing-library/svelte");
    const { default: App } = await import("../App.svelte");
    const { container } = tl.render(App);
    await vi.waitFor(() => expect(container.querySelectorAll(".tile").length).toBe(2));
    expect(tl.screen.getAllByText("Latest from your sites").length).toBeGreaterThan(0);
    expect(tl.screen.queryByRole("combobox", { name: "Page" })).toBeNull();
    expect([...container.querySelectorAll(".site-badge")].map((b) => b.textContent)).toEqual(["D", "G"]);

    for (const o of observers.filter((x) => x.live)) o.cb([{ isIntersecting: true }]);
    await vi.waitFor(() => expect(container.querySelectorAll(".tile").length).toBe(4));
    expect(listPages).toEqual([1, 2]);
    expect(searchCalls).toBe(0);
    await vi.waitFor(() => expect(container.querySelector('[data-testid="more-sentinel"]')).toBeNull());
    expect(tl.screen.getByTestId("end-note")).toBeTruthy();
  });
});
