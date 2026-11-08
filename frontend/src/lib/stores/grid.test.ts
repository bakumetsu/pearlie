import { describe, it, expect } from "vitest";
import { createGrid } from "./grid.svelte";

type Item = { id: string };
const keyOf = (t: Item) => t.id;
type PageRes = { items: Item[]; total: number | null; next_page: number | null };

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("createGrid", () => {
  it("open loads page 1", async () => {
    const grid = createGrid(keyOf);
    await grid.open("k", () =>
      Promise.resolve({ items: [{ id: "a" }, { id: "b" }], total: 2, next_page: 2 }));
    expect(grid.items).toEqual([{ id: "a" }, { id: "b" }]);
    expect(grid.total).toBe(2);
    expect(grid.status).toBe("done");
    expect(grid.hasMore).toBe(true);
  });

  it("loadMore appends page 2 and drops duplicate ids", async () => {
    const grid = createGrid(keyOf);
    const loader = (page: number) =>
      page === 1
        ? Promise.resolve({ items: [{ id: "a" }, { id: "b" }], total: 3, next_page: 2 })
        : Promise.resolve({ items: [{ id: "b" }, { id: "c" }], total: 3, next_page: null });
    await grid.open("k", loader);
    await grid.loadMore();
    expect(grid.items).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }]);
    expect(grid.hasMore).toBe(false);
  });

  it("removeAt / insertAt", async () => {
    const grid = createGrid(keyOf);
    await grid.open("k", () =>
      Promise.resolve({ items: [{ id: "a" }, { id: "b" }, { id: "c" }], total: 3, next_page: null }));

    const removed = grid.removeAt(1);
    expect(removed).toEqual({ id: "b" });
    expect(grid.items).toEqual([{ id: "a" }, { id: "c" }]);
    expect(grid.total).toBe(2);

    expect(grid.removeAt(99)).toBeUndefined();
    expect(grid.items).toEqual([{ id: "a" }, { id: "c" }]);

    grid.insertAt({ id: "b" }, 1);
    expect(grid.items).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }]);
    expect(grid.total).toBe(3);

    grid.insertAt({ id: "b" }, 0); // duplicate → no-op
    expect(grid.items).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }]);

    grid.insertAt({ id: "d" }, 99); // clamps to end
    expect(grid.items).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }]);
    expect(grid.total).toBe(4);
  });

  it("stale response is ignored", async () => {
    const grid = createGrid(keyOf);
    const slow = deferred<PageRes>();
    const p1 = grid.open("a", () => slow.promise);
    await grid.open("b", () =>
      Promise.resolve({ items: [{ id: "x" }], total: 1, next_page: null }));

    slow.resolve({ items: [{ id: "y" }], total: 1, next_page: null });
    await p1;

    expect(grid.items).toEqual([{ id: "x" }]);
    expect(grid.listKey).toBe("b");
  });

  it("open with same key after done does not re-fetch", async () => {
    let calls = 0;
    const grid = createGrid(keyOf);
    const loader = () => { calls++; return Promise.resolve({ items: [{ id: "a" }], total: 1, next_page: null }); };
    await grid.open("k", loader);
    await grid.open("k", loader);
    expect(calls).toBe(1);
  });

  it("loader error sets status/error; retry recovers", async () => {
    let fail = true;
    const grid = createGrid(keyOf);
    const loader = () =>
      fail
        ? Promise.reject(new Error("boom"))
        : Promise.resolve({ items: [{ id: "a" }], total: 1, next_page: null });

    await grid.open("k", loader);
    expect(grid.status).toBe("error");
    expect(grid.error?.message).toBe("boom");

    fail = false;
    await grid.retry();
    expect(grid.status).toBe("done");
    expect(grid.items).toEqual([{ id: "a" }]);
  });

  it("neighbors", async () => {
    const grid = createGrid(keyOf);
    await grid.open("k", () =>
      Promise.resolve({ items: [{ id: "a" }, { id: "b" }, { id: "c" }], total: 3, next_page: null }));

    expect(grid.neighbors("a")).toEqual({ prev: null, next: { id: "b" } });
    expect(grid.neighbors("b")).toEqual({ prev: { id: "a" }, next: { id: "c" } });
    expect(grid.neighbors("c")).toEqual({ prev: { id: "b" }, next: null });
    expect(grid.neighbors("z")).toEqual({ prev: null, next: null });
  });
});
