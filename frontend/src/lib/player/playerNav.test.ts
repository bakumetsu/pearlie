// tests for createPlayerNav with a mocked grid, player, getDetail, navigate, notify
import { describe, it, expect, vi } from "vitest";
import { createPlayerNav, toPlayerItem } from "./playerNav.svelte";
import type { ListGrid } from "../item/listNav";
import type { PlayerItem } from "./player.svelte";

type FakeItem = { kind: string; id: string; [k: string]: unknown };

function item(kind: string, id: string, extra: Record<string, unknown> = {}): never {
  return { kind, id, ...extra } as never;
}

function makeGrid(o: Partial<Omit<ListGrid, "items">> & { items?: never[] } = {}): ListGrid {
  return {
    items: o.items ?? [],
    page: o.page ?? 1,
    pages: o.pages ?? null,
    hasNext: o.hasNext ?? false,
    status: o.status ?? "ready",
    goTo: o.goTo ?? (async () => {}),
    markCrossed: o.markCrossed ?? (() => {}),
  };
}

function playerWith(
  item: PlayerItem | null,
  mode: string,
  swap = vi.fn(),
): { item: PlayerItem | null; mode: string; swap: (i: PlayerItem) => void } {
  return { item, mode, swap };
}

const v1: PlayerItem = { id: "v1", title: "V1", streamUrl: "s1", posterUrl: "t1", href: "/library/videos/v1" };
const v2: PlayerItem = { id: "v2", title: "V2", streamUrl: "s2", posterUrl: "t2", href: "/library/videos/v2" };
const v3: PlayerItem = { id: "v3", title: "V3", streamUrl: "s3", posterUrl: "t3", href: "/library/videos/v3" };

function makeDetail(over: Record<string, unknown> = {}) {
  return {
    kind: "video",
    id: "v2",
    title: "T2",
    stream_url: "http://s2",
    thumb_url: "http://t2",
    fallback_streams: [],
    ...over,
  } as never;
}

describe("toPlayerItem", () => {
  it("returns null for non-video kind", () => {
    expect(toPlayerItem(makeDetail({ kind: "image" }))).toBeNull();
  });

  it("returns null for video without stream_url", () => {
    expect(toPlayerItem(makeDetail({ stream_url: null }))).toBeNull();
  });

  it("returns mapped PlayerItem for valid video", () => {
    const d = makeDetail({ id: "v9", title: "N", stream_url: "http://x", thumb_url: "http://p", fallback_streams: [{ url: "http://fb", mime: "video/mp4" }] });
    const pi = toPlayerItem(d);
    expect(pi).not.toBeNull();
    expect(pi!.id).toBe("v9");
    expect(pi!.title).toBe("N");
    expect(pi!.streamUrl).toBe("http://x");
    expect(pi!.posterUrl).toBe("http://p");
    expect(pi!.fallbacks).toEqual([{ url: "http://fb", mime: "video/mp4" }]);
  });
});

describe("createPlayerNav", () => {
  it("stage next navigates to next video, skipping an image", async () => {
    const grid = makeGrid({
      items: [item("video", "v1"), item("image", "img1"), item("video", "v2")],
      hasNext: false,
    });
    const nav = createPlayerNav({
      player: playerWith(v1, "stage"),
      grid,
      getDetail: async () => makeDetail(),
      navigate: vi.fn(),
      notify: vi.fn(),
    });
    // capture navigate
    const navigate = (grid as never as { _nav?: ReturnType<typeof vi.fn> })._nav;
    // re-create with spy
    const navSpy = vi.fn();
    const grid2 = makeGrid({
      items: [item("video", "v1"), item("image", "img1"), item("video", "v2")],
      hasNext: false,
    });
    const p2 = playerWith(v1, "stage");
    const n2 = createPlayerNav({
      player: p2,
      grid: grid2,
      getDetail: async () => makeDetail(),
      navigate: navSpy,
      notify: vi.fn(),
    });
    expect(n2.canNext()).toBe(true);
    n2.next();
    await vi.waitFor(() => expect(navSpy).toHaveBeenCalled());
    expect(navSpy).toHaveBeenCalledTimes(1);
    // should be v2's href, not img1's
    expect(navSpy.mock.calls[0][0]).toContain("v2");
  });

  it("mini next calls getDetail then player.swap, does not call navigate", async () => {
    const grid = makeGrid({
      items: [item("video", "v1"), item("video", "v2")],
      hasNext: false,
    });
    const getDetail = vi.fn(async () => makeDetail({ id: "v2", title: "T2", stream_url: "http://s2" }));
    const swap = vi.fn();
    const nav = createPlayerNav({
      player: playerWith(v1, "mini", swap),
      grid,
      getDetail,
      navigate: vi.fn(),
      notify: vi.fn(),
    });
    expect(nav.canNext()).toBe(true);
    nav.next();
    await vi.waitFor(() => expect(swap).toHaveBeenCalled());
    expect(getDetail).toHaveBeenCalledWith("videos", "v2");
    expect(swap).toHaveBeenCalledTimes(1);
    const swapped = swap.mock.calls[0][0] as PlayerItem;
    expect(swapped.id).toBe("v2");
    expect(swapped.streamUrl).toBe("http://s2");
  });

  it("mini at last loaded item with hasNext true: canNext false, next() does nothing", async () => {
    const goTo = vi.fn(async () => {});
    const grid = makeGrid({
      items: [item("video", "v1"), item("video", "v2")],
      page: 1,
      hasNext: true,
      goTo,
    });
    const nav = createPlayerNav({
      player: playerWith(v2, "mini"),
      grid,
      getDetail: async () => makeDetail(),
      navigate: vi.fn(),
      notify: vi.fn(),
    });
    expect(nav.canNext()).toBe(false);
    nav.next();
    // give it a tick
    await new Promise((r) => setTimeout(r, 0));
    expect(goTo).not.toHaveBeenCalled();
  });

  it("stage at edge crosses: goTo called", async () => {
    const items: never[] = [item("video", "v1")];
    let crossed = false;
    const grid = makeGrid({
      items,
      page: 1,
      pages: 2,
      hasNext: true,
      goTo: async (p: number) => {
        if (p === 2) {
          items.push(item("video", "v2"));
          (grid as never as { hasNext: boolean }).hasNext = false;
        }
      },
      markCrossed: () => { crossed = true; },
    });
    const nav = createPlayerNav({
      player: playerWith(v1, "stage"),
      grid,
      getDetail: async () => makeDetail(),
      navigate: vi.fn(),
      notify: vi.fn(),
    });
    expect(nav.canNext()).toBe(true);
    nav.next();
    await vi.waitFor(() => expect(crossed).toBe(true));
  });

  it("target null without error sets canNext false afterwards", async () => {
    const items: never[] = [item("video", "v1")];
    const grid = makeGrid({
      items,
      page: 1,
      pages: 2,
      hasNext: true,
      goTo: async (p: number) => {
        // simulate loading a page with no new video items
        (grid as never as { hasNext: boolean }).hasNext = false;
        (grid as never as { page: number }).page = p;
      },
    });
    const nav = createPlayerNav({
      player: playerWith(v1, "stage"),
      grid,
      getDetail: async () => makeDetail(),
      navigate: vi.fn(),
      notify: vi.fn(),
    });
    expect(nav.canNext()).toBe(true);
    nav.next();
    await vi.waitFor(() => expect(nav.canNext()).toBe(false));
  });

  it("target null then new item pushed restores canNext", async () => {
    const items: never[] = [item("video", "v1")];
    const grid = makeGrid({
      items,
      page: 1,
      pages: 2,
      hasNext: true,
      goTo: async (p: number) => {
        // simulate loading a page with no new video items
        (grid as never as { hasNext: boolean }).hasNext = false;
        (grid as never as { page: number }).page = p;
      },
    });
    const nav = createPlayerNav({
      player: playerWith(v1, "stage"),
      grid,
      getDetail: async () => makeDetail(),
      navigate: vi.fn(),
      notify: vi.fn(),
    });
    expect(nav.canNext()).toBe(true);
    nav.next();
    await vi.waitFor(() => expect(nav.canNext()).toBe(false));
    // push another video item onto grid.items
    items.push(item("video", "v2"));
    expect(nav.canNext()).toBe(true);
  });

  it("grid.status error notifies", async () => {
    const notify = vi.fn();
    const grid = makeGrid({
      items: [item("video", "v1")],
      page: 1,
      pages: 2,
      hasNext: true,
      status: "error",
      goTo: async () => {},
    });
    const nav = createPlayerNav({
      player: playerWith(v1, "stage"),
      grid,
      getDetail: async () => makeDetail(),
      navigate: vi.fn(),
      notify,
    });
    nav.next();
    await vi.waitFor(() => expect(notify).toHaveBeenCalledWith("Could not load the next page"));
  });
});
