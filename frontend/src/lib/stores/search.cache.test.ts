import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { cachedSearch, clearSearchAnswers } from "./search.svelte";
import type { Api } from "../api/client";

function makeApi(res: unknown): Api & { search: Mock } {
  return { search: vi.fn().mockResolvedValue(res) } as unknown as Api & { search: Mock };
}

const good = { query: "a", sections: [{ id: "nhentai", items: [] }] };

describe("cachedSearch", () => {
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
    t = 5 * 60 * 1000 + 1;
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
