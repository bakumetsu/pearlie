// @vitest-environment jsdom
// T-49: player bar prev/next, mini player persistence (mocked fetch, no real servers)
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { resetAllGrids } from "../lib/stores/shared.svelte";
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
  await vi.waitFor(() => {
    expect(player.item?.id).toBe(id);
    expect(player.mode).toBe("stage");
    expect(player.slot).not.toBe(null);
  });
}

function getMiniSection(): HTMLElement {
  const s = document.querySelector('section[aria-label="Mini player"]');
  if (!s) throw new Error("Mini player section not found in DOM");
  return s as HTMLElement;
}

async function clickMiniButton(name: string): Promise<void> {
  const section = getMiniSection();
  const btn = Array.from(section.querySelectorAll("button")).find(
    (b) => b.getAttribute("aria-label") === name || b.textContent?.trim() === name,
  );
  if (!btn) throw new Error(`Mini player button "${name}" not found`);
  await fireEvent.click(btn);
}

// ── tests ─────────────────────────────────────────────────────────────────

describe("T-49 player bar prev/next + mini persistence", () => {
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
        const items = [tile(`v${2 * p - 1}`), tile(`v${2 * p}`)];
        const body = {
          items,
          page: p,
          page_size: Number(url.searchParams.get("page_size")),
          total: 4,
          pages: 2,
          next_page: p < 2 ? p + 1 : null,
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
    resetAllGrids();
    history.replaceState({}, "", "/see-all?source=stash_videos");
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("Next video at the page edge loads page 2, replaces history", async () => {
    render(App);
    await openItemFromGrid("v2");

    const historyLenBefore = history.length;

    const nextBtn = screen.getByRole("button", { name: "Next video" });
    await fireEvent.click(nextBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v3");
      expect(history.length).toBe(historyLenBefore);
    });
    await vi.waitFor(() => {
      expect(player.item?.id).toBe("v3");
      expect(player.mode).toBe("stage");
    });
  });

  it("Previous video from the player bar goes to the previous item", async () => {
    render(App);
    await openItemFromGrid("v2");

    const prevBtn = screen.getByRole("button", { name: "Previous video" });
    await fireEvent.click(prevBtn);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v1");
    });
  });

  it("top-bar arrows are gone on a video item", async () => {
    render(App);
    await openItemFromGrid("v2");

    expect(screen.queryByRole("button", { name: "Previous item" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Next item" })).toBeNull();
  });

  it("mini player persists across route changes while paused", async () => {
    render(App);
    await openItemFromGrid("v2");

    history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
    });

    history.pushState({}, "", "/jobs");
    window.dispatchEvent(new PopStateEvent("popstate"));

    await new Promise((r) => setTimeout(r, 50));
    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
      expect(document.querySelector('section[aria-label="Mini player"]')).toBeTruthy();
    });
  });

  it("mini Next video swaps in place without navigating", async () => {
    render(App);
    await openItemFromGrid("v1");

    history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
    });

    await clickMiniButton("Next video");

    await vi.waitFor(() => {
      expect(player.item?.id).toBe("v2");
      expect(player.mode).toBe("mini");
    });
    expect(location.pathname).toBe("/library");
  });

  it("mini closes only on X or ended", async () => {
    render(App);
    await openItemFromGrid("v2");

    history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
    });

    await clickMiniButton("Close player");

    await vi.waitFor(() => {
      expect(player.mode).toBe("hidden");
      expect(player.item).toBeNull();
    });
  });

  it("mini closes when the video ends", async () => {
    render(App);
    await openItemFromGrid("v2");

    history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
    });

    fireEvent(getVideo(), new Event("ended"));

    await vi.waitFor(() => {
      expect(player.mode).toBe("hidden");
    });
  });

  it("mini click returns to the item at the current time, no reload", async () => {
    render(App);
    await openItemFromGrid("v2");
    await vi.waitFor(() => {
      expect(getVideo()).toBeTruthy();
    });

    fireEvent(getVideo(), new Event("playing"));
    setVideoTime(42);

    await new Promise((r) => setTimeout(r, 50));

    history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await vi.waitFor(() => {
      expect(player.mode).toBe("mini");
    });

    const loadCountBefore = loadFn.mock.calls.length;

    const miniLink = document.querySelector('section[aria-label="Mini player"] a.title')!;
    await fireEvent.click(miniLink);

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/videos/v2");
      expect(player.mode).toBe("stage");
    });
    await vi.waitFor(() => {
      expect(player.time).toBe(42);
    });
    await vi.waitFor(() => {
      expect(player.playing).toBe(true);
    });

    expect(loadFn.mock.calls.length).toBe(loadCountBefore);
  });
});
