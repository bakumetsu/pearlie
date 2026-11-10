// @vitest-environment jsdom
// repro tests: single shared See-all list serves images and videos alternately,
// so item prev/next walks the wrong list.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { resetAllGrids } from "../lib/stores/shared.svelte";

// ── fixtures ──────────────────────────────────────────────────────────────

function imageTile(id: string) {
  return {
    kind: "image" as const,
    id,
    title: `img ${id}`,
    thumb_url: `/t/${id}`,
    source: "stash",
    tags: [] as string[],
  };
}

function imageDetail(id: string) {
  return {
    ...imageTile(id),
    full_url: `/f/${id}`,
    tags: [] as string[],
    width: 100,
    height: 100,
  };
}

function videoTile(id: string) {
  return {
    kind: "video" as const,
    id,
    title: `Video ${id}`,
    thumb_url: `/t/${id}.jpg`,
    source: "stash",
    tags: [] as string[],
  };
}

function videoDetail(id: string) {
  return {
    ...videoTile(id),
    stream_url: `/s/${id}.mp4`,
    width: 1920,
    height: 1080,
  };
}

// ── nav helpers (router observes "popstate") ───────────────────────────────

function go(href: string) {
  history.pushState({}, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

async function waitTile(kind: string, id: string) {
  await vi.waitFor(() => {
    const link = Array.from(document.querySelectorAll("a.tile")).find(
      (a) => a.getAttribute("href") === `/item/${kind}/${id}`,
    );
    expect(link).toBeTruthy();
  });
}

async function clickNext() {
  const btn = await screen.findByRole("button", { name: "Next item" });
  expect(btn).toBeTruthy();
  await fireEvent.click(btn);
}

async function clickPrev() {
  const btn = await screen.findByRole("button", { name: "Previous item" });
  expect(btn).toBeTruthy();
  await fireEvent.click(btn);
}

// ── tests ─────────────────────────────────────────────────────────────────

describe("shared See-all list walks wrong list on item nav (repro)", () => {
  let playFn: ReturnType<typeof vi.fn>;
  let pauseFn: ReturnType<typeof vi.fn>;
  let loadFn: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetAllGrids();

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
          new Response(JSON.stringify({}), { status: 404, headers: { "Content-Type": "application/json" } }),
        );
      }

      const imgDetail = url.pathname.match(/^\/api\/library\/stash\/images\/(.+)$/);
      if (imgDetail) {
        return Promise.resolve(
          new Response(JSON.stringify(imageDetail(imgDetail[1])), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }
      const vidDetail = url.pathname.match(/^\/api\/library\/stash\/videos\/(.+)$/);
      if (vidDetail) {
        return Promise.resolve(
          new Response(JSON.stringify(videoDetail(vidDetail[1])), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.pathname === "/api/library/stash/images") {
        const p = Number(url.searchParams.get("page") ?? "1");
        const body = {
          items: [imageTile("i1"), imageTile("i2"), imageTile("i3")],
          page: p,
          page_size: Number(url.searchParams.get("page_size")),
          total: 3,
          pages: 1,
          next_page: null,
        };
        return Promise.resolve(
          new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.pathname === "/api/library/stash/videos") {
        const p = Number(url.searchParams.get("page") ?? "1");
        const body = {
          items: [videoTile("v1"), videoTile("v2"), videoTile("v3")],
          page: p,
          page_size: Number(url.searchParams.get("page_size")),
          total: 3,
          pages: 1,
          next_page: null,
        };
        return Promise.resolve(
          new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      return Promise.resolve(
        new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }),
      );
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  // ── 1: images -> videos -> item(i2): Next/Prev should walk i3, i2, i1 ──
  it("image nav after visiting images then videos", async () => {
    history.replaceState({}, "", "/see-all?source=stash_images");
    render(App);

    await waitTile("images", "i1");

    // visit the videos list so the shared grid gets polluted
    go("/see-all?source=stash_videos");
    await waitTile("videos", "v1");

    // open an image detail
    go("/item/images/i2");
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i2");
    });

    await clickNext();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i3");
    });

    await clickPrev();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i2");
    });

    await clickPrev();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i1");
    });
  });

  // ── 2: videos -> images -> item(v2): Next/Prev should walk v3, v2, v1 ──
  it("video nav after visiting videos then images", async () => {
    history.replaceState({}, "", "/see-all?source=stash_videos");
    render(App);

    await waitTile("videos", "v1");

    // visit the images list so the shared grid gets polluted
    go("/see-all?source=stash_images");
    await waitTile("images", "i1");

    // open a video detail
    go("/item/videos/v2");
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
    });

    await clickNext();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v3");
    });

    await clickPrev();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
    });

    await clickPrev();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v1");
    });
  });

  // ── 3: images -> videos -> images list again: item(i1) Next -> i2 ──
  it("back to the image list after the video list", async () => {
    history.replaceState({}, "", "/see-all?source=stash_images");
    render(App);

    await waitTile("images", "i1");

    go("/see-all?source=stash_videos");
    await waitTile("videos", "v1");

    // back to the images list
    go("/see-all?source=stash_images");
    await waitTile("images", "i1");

    // open the first image detail
    go("/item/images/i1");
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i1");
    });

    await clickNext();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i2");
    });
  });

  // ── 4: source switch inside See-all shows new list and keeps other kind's nav ──
  it("source switch inside See-all shows the new list and keeps the other kind's nav", async () => {
    history.replaceState({}, "", "/see-all?source=stash_images");
    render(App);

    await waitTile("images", "i1");

    go("/see-all?source=stash_videos");
    await waitTile("videos", "v1");
    await waitTile("videos", "v2");
    await waitTile("videos", "v3");

    // no image tiles should remain in the DOM
    await vi.waitFor(() => {
      const imgTiles = Array.from(document.querySelectorAll("a.tile")).filter(
        (a) => a.getAttribute("href")?.startsWith("/item/images/"),
      );
      expect(imgTiles.length).toBe(0);
    });

    // open an image detail (the other kind's nav still works)
    go("/item/images/i2");
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i2");
    });

    await clickNext();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/i3");
    });
  });
});
