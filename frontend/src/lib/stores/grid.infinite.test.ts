import { describe, it, expect, vi } from "vitest";
import { createGrid } from "./grid.svelte";

type Item = { id: string };
type Res = { items: Item[]; total: number; next_page: number | null; page: number; pages: number; page_size: number };
const mk = (page: number, items = [{ id: `p${page}` }]): Res => ({ items, total: 3, next_page: page < 3 ? page + 1 : null, page, pages: 3, page_size: 1 });
const g = () => {
  const grid = createGrid<Item>((t) => t.id);
  grid.setAccumulate(true);
  return grid;
};

describe("grid infinite", () => {
  it("loadMore appends the next page and stops at the last", async () => {
    const loader = vi.fn(async (p: number) => mk(p));
    const grid = g();
    await grid.open("k", loader);
    await grid.loadMore();
    await grid.loadMore();
    expect(grid.items.map((i) => i.id)).toEqual(["p1", "p2", "p3"]);
    expect(grid.page).toBe(1);
    expect(grid.lastPage).toBe(3);
    expect(grid.hasNext).toBe(false);
    await grid.loadMore();
    expect(loader).toHaveBeenCalledTimes(3);
  });

  it("does nothing when accumulate is off", async () => {
    const loader = vi.fn(async (p: number) => mk(p));
    const grid = createGrid<Item>((t) => t.id);
    await grid.open("k", loader);
    await grid.loadMore();
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("a second call while loading makes no second request", async () => {
    let release!: (r: Res) => void;
    const loader = vi.fn(async (p: number) => (p === 1 ? mk(1) : new Promise<Res>((r) => (release = r))));
    const grid = g();
    await grid.open("k", loader);
    const first = grid.loadMore();
    await grid.loadMore();
    expect(loader).toHaveBeenCalledTimes(2);
    release(mk(2));
    await first;
    expect(grid.items).toHaveLength(2);
  });

  it("an error keeps items, blocks auto-repeat, and a forced retry works", async () => {
    let fail = true;
    const loader = vi.fn(async (p: number) => {
      if (p === 2 && fail) throw new Error("x");
      return mk(p);
    });
    const grid = g();
    await grid.open("k", loader);
    await grid.loadMore();
    expect(grid.more).toBe("error");
    expect(grid.status).toBe("done");
    await grid.loadMore();
    expect(loader).toHaveBeenCalledTimes(2);
    fail = false;
    await grid.loadMore(true);
    expect(grid.more).toBe("idle");
    expect(grid.items.map((i) => i.id)).toEqual(["p1", "p2"]);
  });

  it("drops duplicates across pages", async () => {
    const loader = vi.fn(async (p: number) => mk(p, [{ id: "same" }, { id: `p${p}` }]));
    const grid = g();
    await grid.open("k", loader);
    await grid.loadMore();
    expect(grid.items.map((i) => i.id)).toEqual(["same", "p1", "p2"]);
  });

  it("goTo(next page) appends in infinite mode", async () => {
    const grid = g();
    await grid.open("k", vi.fn(async (p: number) => mk(p)));
    await grid.goTo(grid.nextPage);
    expect(grid.items.map((i) => i.id)).toEqual(["p1", "p2"]);
    expect(grid.page).toBe(1);
  });
});
