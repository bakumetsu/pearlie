// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

function tile(id: string) {
  return { kind: "image", id, title: `img ${id}`, thumb_url: `/t/${id}`, source: "stash", tags: [] };
}

type Entries = { isIntersecting: boolean }[];

describe("SeeAll infinite scroll", () => {
  let requested: number[];
  let infinite: boolean;
  let failPage: number | null;
  let tl: typeof import("@testing-library/svelte");
  let observers: { cb: (e: Entries) => void; live: boolean }[];

  // Tell every live observer that the end marker is near
  function nearEnd() {
    for (const o of observers.filter((x) => x.live)) o.cb([{ isIntersecting: true }]);
  }

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
    history.replaceState({}, "", "/see-all?source=stash_images");
    requested = [];
    infinite = true;
    failPage = null;
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      const json = (body: unknown, status = 200) =>
        Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
      if (url.pathname === "/api/options") {
        return json({ sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, source_pace: {}, infinite_scroll: infinite });
      }
      if (url.pathname.startsWith("/api/library/")) {
        const p = Number(url.searchParams.get("page") ?? "1");
        requested.push(p);
        if (p === failPage) {
          failPage = null;
          return json({ error: { code: "boom", message: "boom" } }, 500);
        }
        return json({
          items: [tile(`${p}a`), tile(`${p}b`)],
          page: p,
          page_size: 60,
          total: 6,
          pages: 3,
          next_page: p < 3 ? p + 1 : null,
        });
      }
      return json({}, 404);
    });
  });

  afterEach(() => {
    tl?.cleanup();
    vi.unstubAllGlobals();
  });

  async function firstPage() {
    tl = await import("@testing-library/svelte");
    const { default: App } = await import("../App.svelte");
    const r = tl.render(App);
    await vi.waitFor(() => expect(r.container.querySelectorAll("a.tile").length).toBe(2));
    return r;
  }

  it("off: pager as before, no end marker", async () => {
    infinite = false;
    const { container } = await firstPage();
    expect(tl.screen.getAllByRole("combobox", { name: "Page" })[0]).toBeTruthy();
    expect(container.querySelector('[data-testid="more-sentinel"]')).toBeNull();
    expect(requested).toEqual([1]);
  });

  it("on: no pager, next page loads once near the end and stops at the last page", async () => {
    const { container } = await firstPage();
    expect(tl.screen.queryByRole("combobox", { name: "Page" })).toBeNull();
    expect(container.querySelector('[data-testid="more-sentinel"]')).toBeTruthy();
    expect(requested).toEqual([1]);

    nearEnd();
    await vi.waitFor(() => expect(container.querySelectorAll("a.tile").length).toBe(4));
    expect(requested).toEqual([1, 2]);

    nearEnd();
    await vi.waitFor(() => expect(container.querySelectorAll("a.tile").length).toBe(6));
    expect(requested).toEqual([1, 2, 3]);

    // Last page: the marker is gone and nothing more is asked
    await vi.waitFor(() => expect(container.querySelector('[data-testid="more-sentinel"]')).toBeNull());
    nearEnd();
    await new Promise((r) => setTimeout(r, 20));
    expect(requested).toEqual([1, 2, 3]);
    expect(location.search).not.toContain("page=");
  });

  it("on: an error shows Retry, does not repeat by itself, Retry asks once more", async () => {
    failPage = 2;
    const { container } = await firstPage();
    nearEnd();
    await tl.screen.findByText("Could not load more.");
    nearEnd();
    await new Promise((r) => setTimeout(r, 20));
    expect(requested).toEqual([1, 2]);
    expect(container.querySelectorAll("a.tile").length).toBe(2);

    await tl.fireEvent.click(tl.screen.getByRole("button", { name: "Retry" }));
    await vi.waitFor(() => expect(container.querySelectorAll("a.tile").length).toBe(4));
    expect(requested).toEqual([1, 2, 2]);
  });
});
