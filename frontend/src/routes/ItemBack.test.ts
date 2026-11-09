// T-54: viewer back arrow exits to the originating list
// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { seeAllGrid } from "../lib/stores/shared.svelte";

// ── helpers ───────────────────────────────────────────────────────────────

function tile(id: string) {
  return {
    kind: "video" as const,
    id,
    title: `Video ${id}`,
    thumb_url: `/t/${id}.jpg`,
    source: "stash",
    tags: [] as string[],
  };
}

function detail(id: string) {
  return {
    ...tile(id),
    stream_url: `/s/${id}.mp4`,
    width: 1920,
    height: 1080,
  };
}

async function openItemFromGrid(id: string) {
  await vi.waitFor(() => {
    expect(document.querySelectorAll("a.tile").length).toBeGreaterThan(0);
  });
  const link = Array.from(document.querySelectorAll("a.tile")).find(
    (a) => a.getAttribute("href") === `/item/videos/${id}`,
  )!;
  await fireEvent.click(link);
  await vi.waitFor(() => {
    expect(location.pathname).toBe(`/item/videos/${id}`);
  });
}

// ── tests ─────────────────────────────────────────────────────────────────

describe("T-54 viewer back", () => {
  let loadFn: ReturnType<typeof vi.fn>;
  let playFn: ReturnType<typeof vi.fn>;
  let pauseFn: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // jsdom has no media
    playFn = vi.fn(() => Promise.resolve());
    pauseFn = vi.fn();
    loadFn = vi.fn();
    Object.defineProperty(HTMLMediaElement.prototype, "play", { value: playFn, configurable: true, writable: true });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", { value: pauseFn, configurable: true, writable: true });
    Object.defineProperty(HTMLMediaElement.prototype, "load", { value: loadFn, configurable: true, writable: true });

    // localStorage
    const lsStore = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: (k: string) => lsStore.get(k) ?? null,
        setItem: (k: string, v: string) => { lsStore.set(k, v); },
        removeItem: (k: string) => { lsStore.delete(k); },
        clear: () => { lsStore.clear(); },
        key: (i: number) => [...lsStore.keys()][i] ?? null,
        get length() { return lsStore.size; },
      },
      configurable: true,
      writable: true,
    });

    // IntersectionObserver
    vi.stubGlobal("IntersectionObserver", class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() { return []; }
    });

    // ResizeObserver
    vi.stubGlobal("ResizeObserver", class {
      constructor(private cb: (entries: ResizeObserverEntry[], observer: ResizeObserver) => void) {}
      observe() {
        setTimeout(() => this.cb([], this), 0);
      }
      unobserve() {}
      disconnect() {}
      takeRecords() { return []; }
    });

    window.scrollTo = vi.fn();
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        "http://localhost",
      );
      if (url.pathname === "/api/view-settings") {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 404,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      const detailMatch = url.pathname.match(/^\/api\/library\/videos\/(.+)$/);
      if (detailMatch) {
        const id = detailMatch[1];
        return Promise.resolve(
          new Response(JSON.stringify(detail(id)), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.pathname === "/api/library/stash/videos") {
        const p = Number(url.searchParams.get("page") ?? "1");
        const items = [tile("v1"), tile("v2"), tile("v3")];
        const body = {
          items,
          page: p,
          page_size: Number(url.searchParams.get("page_size")),
          total: 3,
          pages: 1,
          next_page: null,
        };
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });

    // reset app state
    seeAllGrid.reset();
    history.replaceState({}, "", "/see-all?source=stash_videos");
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("back from a paged item lands on the list", async () => {
    render(App);
    await openItemFromGrid("v1");

    const nextBtn = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
    });

    const nextBtn2 = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn2);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v3");
    });

    const backBtn = screen.getByRole("button", { name: "Back" });
    await fireEvent.click(backBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/see-all");
    });
  });

  it("direct link: back goes to the library page", async () => {
    history.replaceState({}, "", "/item/videos/v1");
    render(App);

    const backBtn = await screen.findByRole("button", { name: "Back" });
    await fireEvent.click(backBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/library");
    });
  });
});
