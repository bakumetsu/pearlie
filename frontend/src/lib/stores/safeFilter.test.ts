// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { isHiddenInSafeMode, visibleInSafeMode } from "./safeFilter";
import { createGrid } from "./grid.svelte";
import { sfw } from "./sfw.svelte";
import { options } from "./options.svelte";
import { wallRows } from "../browse/layout";

vi.mock("./options.svelte", () => ({ options: { values: null as unknown } }));

const warn = { source: "danbooru", post_id: "1", thumb_url: "", blur: { tag: "gore" } } as never;
const plain = { source: "danbooru", post_id: "2", thumb_url: "", blur: null } as never;
const key = (t: { post_id: string }) => "danbooru:" + t.post_id;
const setOpts = (v: unknown) => ((options as { values: unknown }).values = v);

afterEach(() => {
  sfw!.set(false);
  setOpts(null);
});

describe("isHiddenInSafeMode", () => {
  it("safe mode off: nothing hidden", () => {
    expect(isHiddenInSafeMode(warn)).toBe(false);
  });
  it("safe mode on, switch off (also while options unloaded): warn hidden, plain kept", () => {
    sfw!.set(true);
    expect(isHiddenInSafeMode(warn)).toBe(true);
    expect(isHiddenInSafeMode(plain)).toBe(false);
    expect(visibleInSafeMode([warn, plain])).toEqual([plain]);
  });
  it("safe mode on, switch on: warn kept", () => {
    sfw!.set(true);
    setOpts({ allow_blurred_tags: true });
    expect(isHiddenInSafeMode(warn)).toBe(false);
  });
});

describe("grid with the safe-mode filter", () => {
  async function loaded() {
    const grid = createGrid<never>(key as never, (i) => !isHiddenInSafeMode(i));
    await grid.open("k", async () => ({ items: [warn, plain], total: 2, next_page: null }), 1);
    return grid;
  }

  it("overlay/paging list and wall rows exclude the hidden post (no hole)", async () => {
    sfw!.set(true);
    const grid = await loaded();
    expect(grid.ids).toEqual(["danbooru:2"]);
    expect(grid.neighbors("danbooru:2")).toEqual({ prev: null, next: null });
    const rows = wallRows(grid.items.map(() => 1), 600, 200, 2);
    expect(rows.flat()).toEqual([0]);
    expect(grid.total).toBe(2);
  });

  it("toggling the switch brings the post back without reloading", async () => {
    sfw!.set(true);
    const grid = await loaded();
    expect(grid.items).toHaveLength(1);
    setOpts({ allow_blurred_tags: true });
    expect(grid.items).toHaveLength(2);
  });
});
