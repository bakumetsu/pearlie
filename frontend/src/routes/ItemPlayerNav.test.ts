// @vitest-environment jsdom
// repro tests for T-46: player state across item navigation (stage, mini, replay)
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { seeAllGrid } from "../lib/stores/shared.svelte";
import { player } from "../lib/player/player.svelte";

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

function getVideo(): HTMLVideoElement {
  const v = document.querySelector<HTMLVideoElement>("video[data-player]");
  if (!v) throw new Error("video[data-player] not found in DOM");
  return v;
}

function setVideoTime(seconds: number) {
  const v = getVideo();
  Object.defineProperty(v, "currentTime", { value: seconds, configurable: true, writable: true });
  fireEvent(v, new Event("timeupdate"));
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
  // debug: assert player state is fully loaded
  await vi.waitFor(() => {
    expect(player.item?.id).toBe(id);
    expect(player.mode).toBe("stage");
    expect(player.slot).not.toBe(null);
  });
}

// ── tests ─────────────────────────────────────────────────────────────────

describe("T-46 player nav repro", () => {
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

  // ── 1a: Next in stage (after "playing") keeps a visible stage ──
  it("Next in stage keeps a visible stage (playing)", async () => {
    render(App);
    await openItemFromGrid("v1");
    await vi.waitFor(() => expect(getVideo()).toBeTruthy());

    fireEvent(getVideo(), new Event("playing"));

    const nextBtn = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
    });
    await vi.waitFor(() => {
      expect(player.item?.id).toBe("v2");
    });

    expect(player.item?.id).toBe("v2");
    expect(player.mode).toBe("stage");
    expect(player.slot).not.toBe(null);
    expect(getVideo().style.display).not.toBe("none");
  });

  // ── 1b: Next in stage (without "playing") keeps a visible stage ──
  it("Next in stage keeps a visible stage (no playing)", async () => {
    render(App);
    await openItemFromGrid("v1");
    await vi.waitFor(() => expect(getVideo()).toBeTruthy());

    // intentionally do NOT dispatch "playing"

    const nextBtn = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
    });
    await vi.waitFor(() => {
      expect(player.item?.id).toBe("v2");
    });

    expect(player.item?.id).toBe("v2");
    expect(player.mode).toBe("stage");
    expect(player.slot).not.toBe(null);
    expect(getVideo().style.display).not.toBe("none");
  });

  // ── 2: Mini player click does not restart ──
  it("Mini player click does not restart", async () => {
    render(App);
    await openItemFromGrid("v1");
    await vi.waitFor(() => expect(getVideo()).toBeTruthy());

    fireEvent(getVideo(), new Event("playing"));
    expect(player.playing).toBe(true);
    setVideoTime(42);
    expect(player.time).toBe(42);

    await new Promise((r) => setTimeout(r, 50)); // let svelte flush before leaving
    // navigate away → mini mode
    history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));

    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
    });

    const loadCountBefore = loadFn.mock.calls.length;

    // click the mini-dock title link
    const miniLink = document.querySelector('section[aria-label="Mini player"] a.title')!;
    await fireEvent.click(miniLink);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v1");
    });
    await vi.waitFor(() => {
      expect(player.item?.id).toBe("v1");
    });

    await vi.waitFor(() => expect(player.mode).toBe("stage"));
    expect(player.time).toBe(42);
    expect(loadFn.mock.calls.length).toBe(loadCountBefore);
  });

  // ── 3: Nav arrow after replay keeps the video ──
  it("Nav arrow after replay keeps the video", async () => {
    render(App);
    await openItemFromGrid("v1");
    await vi.waitFor(() => expect(getVideo()).toBeTruthy());

    const v = getVideo();
    fireEvent(v, new Event("playing"));
    fireEvent(v, new Event("ended"));
    fireEvent(v, new Event("playing")); // replay

    const nextBtn = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
    });
    await vi.waitFor(() => {
      expect(player.item?.id).toBe("v2");
    });

    expect(player.item?.id).toBe("v2");
    expect(player.mode).toBe("stage");
  });
});
