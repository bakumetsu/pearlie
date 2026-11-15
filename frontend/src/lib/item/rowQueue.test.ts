import { describe, it, expect, vi } from "vitest";
import { createGrid } from "../stores/grid.svelte";
import { keyOf } from "../stores/shared.svelte";
import { canStep, stepInList } from "./listNav";
import { seedVideoQueue } from "./rowQueue";
import type { LibraryItem } from "../api/client";

const v = (n: number) => ({ id: "v" + n, kind: "video", title: "t" + n }) as unknown as LibraryItem;
const img = { id: "i1", kind: "image", title: "i" } as unknown as LibraryItem;

describe("seedVideoQueue", () => {
  it("queues the row's videos so Prev/Next step inside the row", async () => {
    const grid = createGrid(keyOf);
    seedVideoQueue("row:x", [v(1), img, v(2), v(3)], vi.fn(), { hasNext: false }, grid);
    expect(grid.items.map(keyOf)).toEqual(["video:v1", "video:v2", "video:v3"]);
    expect(canStep(grid as never, "video:v2", 1, { kind: "video", cross: false })).toBe(true);
    expect(canStep(grid as never, "video:v1", -1, { kind: "video", cross: false })).toBe(false);
    const t = await stepInList(grid as never, "video:v2", 1, { kind: "video", cross: false });
    expect(t?.id).toBe("v3");
  });

  it("fetches the next page of the same list at the row end (stage)", async () => {
    const grid = createGrid(keyOf);
    const loader = vi.fn(async (p: number) => ({ items: [v(4), v(5)], total: 5, next_page: null, page: p }));
    seedVideoQueue("row:x", [v(1), v(2), v(3)], loader as never, { hasNext: true }, grid);
    expect(canStep(grid as never, "video:v3", 1, { kind: "video", cross: false })).toBe(false);
    expect(canStep(grid as never, "video:v3", 1, { kind: "video", cross: true })).toBe(true);
    const t = await stepInList(grid as never, "video:v3", 1, { kind: "video", cross: true });
    expect(loader).toHaveBeenCalledTimes(1);
    expect(loader.mock.calls[0]![0]).toBe(2);
    expect(t?.id).toBe("v4");
    expect(grid.items.map(keyOf)).toEqual(["video:v1", "video:v2", "video:v3", "video:v4", "video:v5"]);
  });
});
