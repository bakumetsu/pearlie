import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { createSearch } from "./search.svelte";
import { ApiError } from "../api/client";
import { parseChip, type Chip, type SearchState } from "../query";
import type { Api, Section } from "../api/client";

function chip(raw: string) {
  const c = parseChip(raw);
  if (!c) throw new Error(`bad chip: ${raw}`);
  return c;
}

function sec(id: string, error?: { code: string; message: string }): Section {
  return { id, ...(error ? { error } : {}) } as Section;
}

function makeApi(): Api & { search: Mock; save: Mock } {
  return { search: vi.fn(), list: vi.fn(), save: vi.fn(), health: vi.fn() } as unknown as Api & { search: Mock; save: Mock };
}

const state = (over: Partial<{ chips: string | Chip[] | false; pill: string; sites: SearchState["sites"] }> = {}): SearchState => ({
  chips: over.chips === false ? [] : (Array.isArray(over.chips) ? over.chips : [chip(over.chips ?? "test")]),
  pill: (over.pill ?? "all") as SearchState["pill"],
  sites: (over.sites ?? ["danbooru"]) as SearchState["sites"],
});

describe("createSearch", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces and calls search once", async () => {
    const api = makeApi();
    api.search.mockResolvedValue({ sections: [] });
    const s = createSearch(api);
    s.run(state());
    expect(api.search).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(300);
    expect(api.search).toHaveBeenCalledTimes(1);
    const [p] = api.search.mock.calls[0];
    expect(p.sources).toEqual(["stash_images", "stash_videos", "komga_books", "danbooru"]);
    expect(p.q).toBe("test");
  });

  it("coalesces two run() calls within the window into one", async () => {
    const api = makeApi();
    api.search.mockResolvedValue({ sections: [] });
    const s = createSearch(api);
    s.run({ chips: [chip("a")], pill: "all", sites: ["danbooru"] });
    s.run({ chips: [chip("b")], pill: "all", sites: ["danbooru"] });
    await vi.advanceTimersByTimeAsync(300);
    expect(api.search).toHaveBeenCalledTimes(1);
    expect(api.search.mock.calls[0][0].q).toBe("b");
  });

  it("immediate:true fires synchronously", () => {
    const api = makeApi();
    api.search.mockResolvedValue({ sections: [] });
    const s = createSearch(api);
    s.run(state(), { immediate: true });
    expect(api.search).toHaveBeenCalledTimes(1);
  });

  it("a newer run aborts the older; late resolve does not overwrite", async () => {
    const api = makeApi();
    const signals: AbortSignal[] = [];
    const resolvers: Array<(v: unknown) => void> = [];
    api.search.mockImplementation((_p: unknown, signal: AbortSignal) => {
      signals.push(signal);
      return new Promise((res) => resolvers.push(res));
    });
    const s = createSearch(api);
    s.run({ chips: [chip("old")], pill: "all", sites: ["danbooru"] }, { immediate: true });
    s.run({ chips: [chip("new")], pill: "all", sites: ["danbooru"] }, { immediate: true });

    expect(signals[0].aborted).toBe(true);

    // Stale resolve – should be ignored
    resolvers[0]({ sections: [sec("stash_images")] });
    // Fresh resolve
    resolvers[1]({ sections: [sec("stash_images"), sec("stash_videos"), sec("komga_books"), sec("danbooru")] });
    await vi.advanceTimersByTimeAsync(0);

    expect(s.sections["stash_videos"]?.status).toBe("done");
    expect(s.sections["komga_books"]?.status).toBe("done");
    expect(s.sections["danbooru"]?.status).toBe("done");
  });

  it("section-level error marks that section error, siblings stay done", async () => {
    const api = makeApi();
    api.search.mockResolvedValue({
      sections: [sec("stash_images"), sec("danbooru", { code: "boom", message: "upstream 502" })],
    });
    const s = createSearch(api);
    s.run({ chips: [chip("x")], pill: "all", sites: ["danbooru"] }, { immediate: true });
    await vi.advanceTimersByTimeAsync(0);

    expect(s.sections["stash_images"]?.status).toBe("done");
    expect(s.sections["danbooru"]?.status).toBe("error");
    expect(s.sections["danbooru"]?.error).toBe("upstream 502");
  });

  it("non-abort rejection sets banner", async () => {
    const api = makeApi();
    api.search.mockRejectedValue(new Error("x"));
    const s = createSearch(api);
    s.run(state(), { immediate: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(s.banner).toBe("Search failed");
  });

  it("no chips: site rows first, library rows below, sent once", () => {
    const api = makeApi();
    api.search.mockResolvedValue({ sections: [] });
    const s = createSearch(api);
    const st: SearchState = { chips: [], pill: "all", sites: ["danbooru", "gelbooru"] };
    s.run(st, { immediate: true });
    s.run(st, { immediate: true });
    expect(api.search).toHaveBeenCalledTimes(1);
    expect(api.search.mock.calls[0][0].q).toBe("");
    expect(api.search.mock.calls[0][0].sources).toEqual([
      "danbooru", "gelbooru", "stash_images", "stash_videos", "komga_books",
    ]);
    expect(Object.keys(s.sections)).toEqual([
      "danbooru", "gelbooru", "stash_images", "stash_videos", "komga_books",
    ]);
  });

  it("retrySection requests only that id", async () => {
    const api = makeApi();
    api.search
      .mockResolvedValueOnce({ sections: [sec("stash_images"), sec("danbooru")] })
      .mockResolvedValueOnce({ sections: [sec("danbooru")] });
    const s = createSearch(api);
    s.run({ chips: [chip("q")], pill: "all", sites: ["danbooru"] }, { immediate: true });
    await vi.advanceTimersByTimeAsync(0);

    s.retrySection("danbooru");
    await vi.advanceTimersByTimeAsync(0);

    expect(api.search).toHaveBeenCalledTimes(2);
    expect(api.search.mock.calls[1][0].sources).toEqual(["danbooru"]);
    expect(s.sections["danbooru"]?.status).toBe("done");
  });

  it("save handles 409 / 422 / 500 / success", async () => {
    const api = makeApi();
    const s = createSearch(api);
    const item = { source: "danbooru", post_id: "123" } as unknown as Parameters<ReturnType<typeof createSearch>["save"]>[0];

    api.save.mockRejectedValueOnce(new ApiError(409, "conflict", "In library", { kind: "image", id: "7" }));
    expect(await s.save(item)).toEqual({ result: "in_library", ref: { kind: "image", id: "7" } });
    expect(s.saveStateOf(item)).toEqual({ state: "in_library", ref: { kind: "image", id: "7" } });

    api.save.mockRejectedValueOnce(new ApiError(422, "blocked", "Blocked"));
    expect(await s.save(item)).toEqual({ result: "blocked" });
    expect(s.saveStateOf(item)).toEqual({ state: "blocked" });

    api.save.mockRejectedValueOnce(new ApiError(500, "error", "Server error"));
    expect(await s.save(item)).toEqual({ result: "error", message: "Server error" });
    expect(s.saveStateOf(item)).toBeUndefined();

    api.save.mockResolvedValueOnce({} as unknown);
    expect(await s.save(item)).toEqual({ result: "queued" });
    expect(s.saveStateOf(item)).toEqual({ state: "queued" });
  });
});
