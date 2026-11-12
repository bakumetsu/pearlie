import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { createSearch } from "./search.svelte";
import { parseChip, type SearchState } from "../query";
import type { Api } from "../api/client";

function makeApi(): Api & { search: Mock } {
  return { search: vi.fn(), list: vi.fn(), save: vi.fn(), health: vi.fn() } as unknown as Api & { search: Mock };
}

function state(raw: string): SearchState {
  const c = parseChip(raw);
  if (!c) throw new Error(`bad chip: ${raw}`);
  return { chips: [c], pill: "all", sites: ["danbooru"] };
}

describe("createSearch identical query", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("does not re-send an identical query, but retryAll forces it", () => {
    const api = makeApi();
    api.search.mockResolvedValue({ sections: [] });
    const s = createSearch(api);
    s.run(state("cat"), { immediate: true });
    s.run(state("cat"), { immediate: true });
    expect(api.search).toHaveBeenCalledTimes(1);
    s.run(state("dog"), { immediate: true });
    expect(api.search).toHaveBeenCalledTimes(2);
    s.retryAll();
    expect(api.search).toHaveBeenCalledTimes(3);
  });

  it("rebuilds sections when the pill changes", () => {
    const api = makeApi();
    api.search.mockResolvedValue({ sections: [] });
    const s = createSearch(api);
    const chip = parseChip("cat")!;
    s.run({ chips: [chip], pill: "all", sites: ["danbooru"] }, { immediate: true });
    expect(Object.keys(s.sections).sort()).toEqual(["danbooru", "komga_books", "stash_images", "stash_videos"]);
    s.run({ chips: [chip], pill: "videos", sites: ["danbooru"] }, { immediate: true });
    expect(Object.keys(s.sections)).toEqual(["stash_videos"]);
    s.run({ chips: [chip], pill: "all", sites: ["danbooru"] }, { immediate: true });
    expect(Object.keys(s.sections).length).toBe(4);
  });
});
