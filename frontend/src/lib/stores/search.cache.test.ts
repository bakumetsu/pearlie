import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { cachedSearch, clearSearchAnswers, createSearch } from "./search.svelte";
import type { Api } from "../api/client";

function makeApi(res: unknown): Api & { search: Mock } {
  return { search: vi.fn().mockResolvedValue(res) } as unknown as Api & { search: Mock };
}

const good = { query: "a", sections: [{ id: "nhentai", items: [] }] };

describe("cachedSearch", () => {
  it("clearSearchAnswers also clears the merged row answers", async () => {
    const { createMergedRow } = await import("./mergedRow.svelte");
    const api = { mergedRow: vi.fn().mockResolvedValue({ items: [], sites: [{ id: "danbooru", state: "ok" }], hidden: 0, pending: false }) } as unknown as Api;
    createMergedRow(api).load({ key: "merged:a:open" });
    await vi.waitFor(() => expect(api.mergedRow).toHaveBeenCalledTimes(1));
    createMergedRow(api).load({ key: "merged:a:open" });
    expect(api.mergedRow).toHaveBeenCalledTimes(1);
    clearSearchAnswers();
    createMergedRow(api).load({ key: "merged:a:open" });
    expect(api.mergedRow).toHaveBeenCalledTimes(2);
  });

  beforeEach(() => clearSearchAnswers());

  it("Back reuses the stored answer without a new request", async () => {
    const api = makeApi(good);
    const p = { q: "a", sources: ["nhentai"], page: 2, page_size: 25 };
    await cachedSearch(api, p);
    const again = await cachedSearch(api, p);
    expect(again).toBe(good);
    expect(api.search).toHaveBeenCalledTimes(1);
  });

  it("a different key or an expired answer asks again", async () => {
    const api = makeApi(good);
    let t = 0;
    const now = () => t;
    await cachedSearch(api, { q: "a", sources: ["nhentai"], page: 1 }, undefined, now);
    await cachedSearch(api, { q: "a", sources: ["nhentai"], page: 2 }, undefined, now);
    expect(api.search).toHaveBeenCalledTimes(2);
    t = 10 * 60 * 1000 + 1;
    await cachedSearch(api, { q: "a", sources: ["nhentai"], page: 1 }, undefined, now);
    expect(api.search).toHaveBeenCalledTimes(3);
  });

  it("errors and library sources are not kept", async () => {
    const bad = makeApi({ query: "a", sections: [{ id: "nhentai", error: { code: "rate_limited", message: "slow" } }] });
    await cachedSearch(bad, { q: "a", sources: ["nhentai"] });
    await cachedSearch(bad, { q: "a", sources: ["nhentai"] });
    expect(bad.search).toHaveBeenCalledTimes(2);
    const lib = makeApi({ query: "a", sections: [{ id: "stash_images", items: [] }] });
    await cachedSearch(lib, { q: "a", sources: ["stash_images"] });
    await cachedSearch(lib, { q: "a", sources: ["stash_images"] });
    expect(lib.search).toHaveBeenCalledTimes(2);
  });
});

describe("cachedSearch invalidation", () => {
  beforeEach(() => clearSearchAnswers());

  it("a save makes the next identical search ask again", async () => {
    const api = { ...makeApi(good), save: vi.fn().mockResolvedValue({}) } as unknown as Api & { search: Mock };
    const p = { q: "a", sources: ["nhentai"] };
    await cachedSearch(api, p);
    await cachedSearch(api, p);
    expect(api.search).toHaveBeenCalledTimes(1);
    await createSearch(api).save({ source: "nhentai", post_id: "1" } as never);
    await cachedSearch(api, p);
    expect(api.search).toHaveBeenCalledTimes(2);
  });
});
