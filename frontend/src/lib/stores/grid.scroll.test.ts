import { describe, it, expect, vi } from "vitest";
import { createGrid } from "./grid.svelte";

// D-31 card 3, test 11 (store part): the scroll place round-trips and a long list keeps seenKeys right.

type Item = { id: string };
const keyOf = (t: Item) => t.id;
const page = (n: number, size: number) => ({
  items: Array.from({ length: size }, (_u, i) => ({ id: `i${(n - 1) * size + i}` })),
  total: 6000,
  next_page: n + 1,
  page: n,
  pages: 100,
  page_size: size,
  stats: null,
  hidden: 0,
});

describe("grid scroll place", () => {
  it("setScroll keeps y, key, offset and sig; setScrollY keeps the anchor", () => {
    const grid = createGrid(keyOf);
    grid.setScroll({ y: 1200, key: "image:7", offset: 14, sig: "wall|3|1000" });
    expect(grid.scrollY).toBe(1200);
    expect(grid.scrollKey).toBe("image:7");
    expect(grid.scrollOffset).toBe(14);
    expect(grid.scrollSig).toBe("wall|3|1000");
    grid.setScrollY(0);
    expect(grid.scrollKey).toBe("image:7");
  });

  it("snapshot then restoreSnapshot round trips the place", async () => {
    const grid = createGrid(keyOf);
    await grid.open("k", vi.fn(async (p: number) => page(p, 5)));
    grid.setScroll({ y: 900, key: "i3", offset: 6, sig: "grid|3|800" });
    const snap = grid.snapshot();
    grid.reset();
    expect(grid.scrollY).toBe(0);
    expect(grid.scrollKey).toBeNull();
    grid.restoreSnapshot(snap);
    expect(grid.scrollY).toBe(900);
    expect(grid.scrollKey).toBe("i3");
    expect(grid.scrollOffset).toBe(6);
    expect(grid.scrollSig).toBe("grid|3|800");
  });

  it("an old snapshot without the anchor fields restores a clean place", () => {
    const grid = createGrid(keyOf);
    grid.setScroll({ y: 5, key: "x", offset: 1, sig: "s" });
    const snap = grid.snapshot();
    delete snap.scrollKey;
    delete snap.scrollOffset;
    delete snap.scrollSig;
    grid.restoreSnapshot(snap);
    expect(grid.scrollKey).toBeNull();
    expect(grid.scrollSig).toBe("");
  });

  it("loadMore over 5,000 items keeps seenKeys right (no cap)", async () => {
    const grid = createGrid(keyOf);
    const loader = vi.fn(async (p: number) => page(p, 100));
    await grid.open("k", loader);
    grid.setAccumulate(true);
    for (let i = 0; i < 49; i++) await grid.loadMore();
    expect(grid.items.length).toBe(5000);
    expect(new Set(grid.ids).size).toBe(5000);
    // A repeated page adds nothing.
    loader.mockImplementationOnce(async () => ({ ...page(1, 100), page: 51, next_page: 52 }));
    await grid.loadMore();
    expect(grid.items.length).toBe(5000);
  });
});
