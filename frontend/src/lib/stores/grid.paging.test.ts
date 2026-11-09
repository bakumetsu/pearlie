import { describe, it, expect, vi } from "vitest";
import { createGrid } from "./grid.svelte";

type Item = { id: string };
type Res = { items: Item[]; total: number; next_page: number | null; page: number; pages: number; page_size: number; stats: { megapixels?: number | null; size_bytes?: number | null } | null; hidden: number };
const keyOf = (t: Item) => t.id;
const mk = (page: number, extra: Partial<Res> = {}): Res => ({ items: [{ id: `p${page}` }], total: 10, next_page: null, page, pages: 2, page_size: 5, stats: null, hidden: 0, ...extra });
const g = () => createGrid(keyOf);

describe("grid paging", () => {
  it("open calls loader with page 3", async () => {
    const loader = vi.fn(async () => mk(3));
    const grid = g();
    await grid.open("k", loader, 3);
    expect(loader).toHaveBeenCalledWith(3, expect.any(AbortSignal));
  });
  it("goTo(2) replaces items", async () => {
    const grid = g();
    await grid.open("k", vi.fn(async (p: number) => mk(p)));
    await grid.goTo(2);
    expect(grid.items).toEqual([{ id: "p2" }]);
  });
  it("goTo aborts slow in-flight load", async () => {
    let resolve1: (v: Res) => void;
    const p1 = new Promise<Res>((r) => (resolve1 = r));
    let call = 0;
    const loader = vi.fn(async (): Promise<Res> => { call++; return call === 1 ? p1 : mk(2); });
    const grid = g();
    const openP = grid.open("k", loader);
    await grid.goTo(2);
    resolve1!(mk(1));
    await openP;
    expect(grid.items).toEqual([{ id: "p2" }]);
  });
  it("served page differs from requested", async () => {
    const grid = g();
    await grid.open("k", vi.fn(async () => mk(4)), 9);
    expect(grid.page).toBe(4);
    expect(grid.requested).toBe(9);
  });
  it("stores pages/perPage/stats/hidden", async () => {
    const stats = { megapixels: 12, size_bytes: 99 };
    const grid = g();
    await grid.open("k", vi.fn(async (p: number) => mk(p, { pages: 7, page_size: 10, stats, hidden: 3 })));
    expect(grid.pages).toBe(7);
    expect(grid.perPage).toBe(10);
    expect(grid.stats).toEqual(stats);
    expect(grid.hidden).toBe(3);
  });
  it("hasNext from next_page", async () => {
    const grid = g();
    await grid.open("k", vi.fn(async (p: number) => mk(p, { next_page: p === 1 ? 2 : null })));
    expect(grid.hasNext).toBe(true);
    await grid.goTo(2);
    expect(grid.hasNext).toBe(false);
  });
  it("open same key+page done: no refetch; different page does", async () => {
    const loader = vi.fn(async (p: number) => mk(p));
    const grid = g();
    await grid.open("k", loader);
    expect(loader).toHaveBeenCalledTimes(1);
    await grid.open("k", loader);
    expect(loader).toHaveBeenCalledTimes(1);
    await grid.open("k", loader, 2);
    expect(loader).toHaveBeenCalledTimes(2);
  });
  it("retry after error refetches requested page", async () => {
    let call = 0;
    const loader = vi.fn(async (p: number) => { call++; if (call === 1) throw new Error("x"); return mk(p); });
    const grid = g();
    await grid.open("k", loader, 3);
    expect(grid.status).toBe("error");
    await grid.retry();
    expect(loader).toHaveBeenLastCalledWith(3, expect.any(AbortSignal));
    expect(grid.status).toBe("done");
  });
  it("removeAt recomputes pages", async () => {
    const items = Array.from({ length: 60 }, (_, i) => ({ id: `i${i}` }));
    const grid = g();
    await grid.open("k", vi.fn(async () => mk(1, { items, total: 61, pages: 2, page_size: 60, next_page: 2 })));
    expect(grid.total).toBe(61);
    expect(grid.pages).toBe(2);
    grid.removeAt(0);
    expect(grid.total).toBe(60);
    expect(grid.pages).toBe(1);
  });
  it("goTo before open is a no-op", async () => {
    const grid = g();
    await grid.goTo(2);
    expect(grid.items).toEqual([]);
    expect(grid.status).toBe("idle");
  });
  it("snapshot then restoreSnapshot on reset grid", async () => {
    const grid = g();
    await grid.open("k", vi.fn(async (p: number) => mk(p, { total: 5, pages: 2, page_size: 3 })), 2);
    const snap = grid.snapshot();
    grid.reset();
    expect(grid.items).toEqual([]);
    expect(grid.status).toBe("idle");
    grid.restoreSnapshot(snap);
    expect(grid.items).toEqual([{ id: "p2" }]);
    expect(grid.page).toBe(2);
    expect(grid.total).toBe(5);
  });
});
