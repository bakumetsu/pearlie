import { describe, it, expect } from "vitest";
import { createGrid } from "./grid.svelte";

type Item = { id: string };

function makeItems(): Item[] {
  return [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }, { id: "e" }];
}

async function openGrid(grid: ReturnType<typeof createGrid<Item>>) {
  const items = makeItems();
  await grid.open("k", async () => ({
    items,
    total: 5,
    next_page: null,
  }));
}

describe("grid removeById / restore", () => {
  it("removeById returns the item and its original index", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    const result = grid.removeById("c");
    expect(result).toEqual({ item: { id: "c" }, index: 2 });
    expect(grid.items.map((i) => i.id)).toEqual(["a", "b", "d", "e"]);
    expect(grid.total).toBe(4);
  });

  it("restore puts the item back at the recorded index", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    const entry = grid.removeById("c")!;
    grid.restore(entry);
    expect(grid.items.map((i) => i.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(grid.total).toBe(5);
  });

  it("removeById of a missing id returns null", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    expect(grid.removeById("z")).toBeNull();
  });

  it("restore clamps when the list shrank in front (no duplicate)", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    // Remove 'a' (front) then 'c'.  Entry for 'c' captured at its then-index.
    grid.removeById("a");
    const entry = grid.removeById("c")!;
    // entry.index is 1 (c was at index 1 after removing a).
    // List is now [b, d, e].  Restore at index 1 → [b, c, d, e].
    grid.restore(entry);
    expect(grid.items.map((i) => i.id)).toEqual(["b", "c", "d", "e"]);
    expect(grid.items.filter((i) => i.id === "c")).toHaveLength(1);
    expect(grid.total).toBe(4);

    // Also verify clamping with an out-of-bounds index:
    // Remove c again, then restore with a stale index larger than the list.
    const entry2 = grid.removeById("c")!; // list [b, d, e], index 1
    grid.restore({ item: entry2.item, index: 99 });
    expect(grid.items.map((i) => i.id)).toEqual(["b", "d", "e", "c"]);
    expect(grid.items.filter((i) => i.id === "c")).toHaveLength(1);
  });

  it("restore twice does not duplicate", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    const entry = grid.removeById("c")!;
    grid.restore(entry);
    grid.restore(entry);
    expect(grid.items.filter((i) => i.id === "c")).toHaveLength(1);
    expect(grid.items.map((i) => i.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(grid.total).toBe(5);
  });

  it("restore of the first item (index 0)", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    const entry = grid.removeById("a")!;
    expect(entry.index).toBe(0);
    grid.restore(entry);
    expect(grid.items.map((i) => i.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(grid.total).toBe(5);
  });

  it("restore of the last item", async () => {
    const grid = createGrid<Item>((t) => t.id);
    await openGrid(grid);
    const entry = grid.removeById("e")!;
    expect(entry.index).toBe(4);
    grid.restore(entry);
    expect(grid.items.map((i) => i.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(grid.total).toBe(5);
  });
});
