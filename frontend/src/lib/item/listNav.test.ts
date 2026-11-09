import { describe, it, expect, vi } from "vitest";
import type { LibraryItem, WebItem } from "../api/client";
import { nearestInList, canStep, stepInList } from "./listNav";
import type { ListGrid } from "./listNav";

function lib(id: string, kind = "video"): LibraryItem {
  return { id, kind } as unknown as LibraryItem;
}

function webItem(postId: number): WebItem {
  return { post_id: postId } as unknown as WebItem;
}

type PageEntry = { items: (LibraryItem | WebItem)[]; status?: string };

function makeGrid(pages: Record<number, PageEntry>, startPage = 1) {
  const entry = pages[startPage];
  const grid = {
    items: entry.items as (LibraryItem | WebItem)[],
    page: startPage,
    pages: Object.keys(pages).length,
    hasNext: pages[startPage + 1] !== undefined,
    status: entry.status ?? "ready",
    goTo: vi.fn(async (page: number) => {
      const p = pages[page];
      if (!p) {
        grid.status = "error";
        return;
      }
      grid.items = p.items;
      grid.page = page;
      grid.status = p.status ?? "ready";
      grid.hasNext = pages[page + 1] !== undefined;
    }),
    markCrossed: vi.fn(),
  } as ListGrid;
  return { grid, goTo: grid.goTo as ReturnType<typeof vi.fn>, markCrossed: grid.markCrossed as ReturnType<typeof vi.fn> };
}

describe("nearestInList", () => {
  it("skips web items", () => {
    const items = [lib("1"), webItem(99), lib("2"), lib("3")];
    expect(nearestInList(items, 0, 1)).toBe(items[2]);
    expect(nearestInList(items, 2, -1)).toBe(items[0]);
  });

  it("honors kind filter", () => {
    const items = [lib("1", "image"), lib("2", "video"), lib("3", "video")];
    expect(nearestInList(items, 0, 1, "video")).toBe(items[1]);
    expect(nearestInList(items, 2, -1, "video")).toBe(items[1]);
  });

  it("returns null when no match remains", () => {
    const items = [lib("1", "image"), webItem(1)];
    expect(nearestInList(items, 0, 1, "video")).toBeNull();
  });
});

describe("canStep", () => {
  it("false when key not in list", () => {
    const { grid } = makeGrid({ 1: { items: [lib("1")] } });
    expect(canStep(grid, "video:999", 1, { cross: true })).toBe(false);
  });

  it("true when a matching item exists on the same page", () => {
    const { grid } = makeGrid({ 1: { items: [lib("1"), lib("2")] } });
    expect(canStep(grid, "video:1", 1, { cross: true })).toBe(true);
  });

  it("true across a page edge only when cross", () => {
    const { grid } = makeGrid({
      1: { items: [lib("1")] },
      2: { items: [lib("2")] },
    });
    expect(canStep(grid, "video:1", 1, { cross: true })).toBe(true);
    expect(canStep(grid, "video:1", 1, { cross: false })).toBe(false);
  });
});

describe("stepInList", () => {
  it("returns next video inside the page without paging", async () => {
    const { grid, goTo } = makeGrid({ 1: { items: [lib("1"), lib("2"), lib("3")] } });
    const result = await stepInList(grid, "video:1", 1, { cross: true });
    expect(result).toEqual(lib("2"));
    expect(goTo).not.toHaveBeenCalled();
  });

  it("crossing forward picks the first video of the next page and calls markCrossed", async () => {
    const { grid, goTo, markCrossed } = makeGrid({
      1: { items: [lib("1"), lib("2")] },
      2: { items: [webItem(10), lib("3"), lib("4")] },
    });
    const result = await stepInList(grid, "video:2", 1, { cross: true });
    expect(result).toEqual(lib("3"));
    expect(goTo).toHaveBeenCalledWith(2);
    expect(markCrossed).toHaveBeenCalled();
  });

  it("backward picks the last video of the previous page", async () => {
    const { grid, goTo, markCrossed } = makeGrid({
      1: { items: [lib("1"), lib("2"), lib("3")] },
      2: { items: [lib("4")] },
    }, 2);
    const result = await stepInList(grid, "video:4", -1, { cross: true });
    expect(result).toEqual(lib("3"));
    expect(goTo).toHaveBeenCalledWith(1);
    expect(markCrossed).toHaveBeenCalled();
  });

  it("a page with no video continues to the following page", async () => {
    const { grid, goTo } = makeGrid({
      1: { items: [lib("1")] },
      2: { items: [webItem(10), webItem(11)] },
      3: { items: [lib("2")] },
    });
    const result = await stepInList(grid, "video:1", 1, { cross: true });
    expect(result).toEqual(lib("2"));
    expect(goTo).toHaveBeenCalledTimes(2);
    expect(goTo).toHaveBeenNthCalledWith(1, 2);
    expect(goTo).toHaveBeenNthCalledWith(2, 3);
  });

  it("cap of 3 pages returns null and restores the original page", async () => {
    const { grid, goTo } = makeGrid({
      1: { items: [lib("1")] },
      2: { items: [webItem(1)] },
      3: { items: [webItem(2)] },
      4: { items: [webItem(3)] },
    });
    const result = await stepInList(grid, "video:1", 1, { cross: true });
    expect(result).toBeNull();
    // went to 2,3,4 then restored to 1
    expect(goTo).toHaveBeenNthCalledWith(1, 2);
    expect(goTo).toHaveBeenNthCalledWith(2, 3);
    expect(goTo).toHaveBeenNthCalledWith(3, 4);
    expect(goTo).toHaveBeenNthCalledWith(4, 1);
    expect(grid.page).toBe(1);
  });

  it("goTo error returns null and restores", async () => {
    const { grid, goTo } = makeGrid({
      1: { items: [lib("1")] },
      2: { items: [], status: "error" },
    });
    const result = await stepInList(grid, "video:1", 1, { cross: true });
    expect(result).toBeNull();
    expect(goTo).toHaveBeenNthCalledWith(1, 2);
    expect(goTo).toHaveBeenNthCalledWith(2, 1);
    expect(grid.page).toBe(1);
  });

  it("cross:false at the edge returns null without goTo", async () => {
    const { grid, goTo } = makeGrid({
      1: { items: [lib("1")] },
      2: { items: [lib("2")] },
    });
    const result = await stepInList(grid, "video:1", 1, { cross: false });
    expect(result).toBeNull();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("kind filter skips an image", async () => {
    const { grid } = makeGrid({ 1: { items: [lib("1", "image"), lib("2", "video")] } });
    const result = await stepInList(grid, "image:1", 1, { cross: true, kind: "video" });
    expect(result).toEqual(lib("2"));
  });

  it("single-flight: concurrent cross-page calls yield one item and one null", async () => {
    const pages: Record<number, PageEntry> = {
      1: { items: [lib("1"), lib("2")] },
      2: { items: [lib("3")] },
    };
    const grid = {
      items: pages[1]!.items as (LibraryItem | WebItem)[],
      page: 1,
      pages: 2,
      hasNext: true,
      status: "ready",
      goTo: vi.fn(async (page: number) => {
        await new Promise((r) => setTimeout(r, 0));
        const p = pages[page];
        if (!p) { grid.status = "error"; return; }
        grid.items = p.items;
        grid.page = page;
        grid.status = p.status ?? "ready";
        grid.hasNext = pages[page + 1] !== undefined;
      }),
      markCrossed: vi.fn(),
    } as ListGrid;

    const p1 = stepInList(grid, "video:2", 1, { cross: true });
    const p2 = stepInList(grid, "video:2", 1, { cross: true });
    const [r1, r2] = await Promise.all([p1, p2]);

    const nonNull = [r1, r2].filter((r) => r !== null);
    expect(nonNull).toHaveLength(1);
    expect(nonNull[0]).toEqual(lib("3"));
    expect(grid.goTo).toHaveBeenCalledTimes(1);
  });
});
