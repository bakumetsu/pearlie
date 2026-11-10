import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Api } from "../api/client";
import { toasts } from "./toasts.svelte";
import { createViewSettings, PLACEHOLDER } from "./viewSettings.svelte";

function makeApi(overrides: Partial<Record<string, unknown>> = {}): Api & Record<string, unknown> {
  const api: Record<string, unknown> = {
    getViewSettings: vi.fn().mockResolvedValue({ sources: {} }),
    putViewSetting: vi.fn().mockImplementation((_source: string, body: { mode: string; per_page: number; zoom: number }) =>
      Promise.resolve({ mode: body.mode, per_page: body.per_page, zoom: body.zoom, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200, modes: ["grid", "wall", "masonry", "list"] }),
    ),
    ...overrides,
  };
  return api as unknown as Api & Record<string, unknown>;
}

describe("viewSettings store", () => {
  beforeEach(() => {
    toasts.dismiss();
  });

  it("has defaults before load", () => {
    const store = createViewSettings();
    expect(store.ready).toBe(false);
    expect(store.get("danbooru")).toEqual(PLACEHOLDER);
    expect(store.get("stash_images")).toEqual(PLACEHOLDER);
  });

  it("load merges server values and sets ready", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          danbooru: { mode: "list", per_page: 40, zoom: 5, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200, modes: ["grid", "wall", "masonry", "list"] },
        },
      }),
    });
    const store = createViewSettings();
    await store.load(api);

    expect(store.ready).toBe(true);
    expect(store.sources.danbooru).toEqual({ mode: "list", per_page: 40, zoom: 5, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200, modes: ["grid", "wall", "masonry", "list"] });
    // Server omitted stash_images, so placeholder is returned
    expect(store.get("stash_images")).toEqual(PLACEHOLDER);
  });

  it("load failure keeps defaults and sets ready true without throwing", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockRejectedValue(new Error("network down")),
    });
    const store = createViewSettings();
    await expect(store.load(api)).resolves.toBeUndefined();

    expect(store.ready).toBe(true);
    expect(store.get("danbooru")).toEqual(PLACEHOLDER);
    expect(store.get("stash_images")).toEqual(PLACEHOLDER);
  });

  it("load twice calls getViewSettings once", async () => {
    const api = makeApi();
    const store = createViewSettings();
    await store.load(api);
    await store.load(api);
    expect(api.getViewSettings).toHaveBeenCalledTimes(1);
  });

  it("set updates local at once and PUT body has the full triple", async () => {
    const api = makeApi();
    const store = createViewSettings();
    await store.load(api);

    const result = await store.set("danbooru", { mode: "list", per_page: 100, zoom: 5 });
    expect(result).toBe(true);
    expect(store.sources.danbooru).toMatchObject({ mode: "list", per_page: 100, zoom: 5 });
    expect(api.putViewSetting).toHaveBeenCalledWith("danbooru", { mode: "list", per_page: 100, zoom: 5 });
  });

  it("set with invalid per_page returns false, no PUT, value unchanged", async () => {
    // per_page 0
    const api0 = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          gelbooru: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100], per_page_max: 100, modes: ["grid", "wall", "masonry", "list"] },
        },
      }),
    });
    const s0 = createViewSettings();
    await s0.load(api0);
    const before0 = { ...s0.sources.gelbooru };
    const r0 = await s0.set("gelbooru", { per_page: 0 });
    expect(r0).toBe(false);
    expect(api0.putViewSetting).not.toHaveBeenCalled();
    expect(s0.sources.gelbooru).toEqual(before0);

    // per_page 61.5 (not a whole number)
    const apiF = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          gelbooru: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100], per_page_max: 100, modes: ["grid", "wall", "masonry", "list"] },
        },
      }),
    });
    const sF = createViewSettings();
    await sF.load(apiF);
    const beforeF = { ...sF.sources.gelbooru };
    const rF = await sF.set("gelbooru", { per_page: 61.5 });
    expect(rF).toBe(false);
    expect(apiF.putViewSetting).not.toHaveBeenCalled();
    expect(sF.sources.gelbooru).toEqual(beforeF);

    // per_page 101 for gelbooru (cap is 100)
    const apiC = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          gelbooru: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100], per_page_max: 100, modes: ["grid", "wall", "masonry", "list"] },
        },
      }),
    });
    const sC = createViewSettings();
    await sC.load(apiC);
    const beforeC = { ...sC.sources.gelbooru };
    const rC = await sC.set("gelbooru", { per_page: 101 });
    expect(rC).toBe(false);
    expect(apiC.putViewSetting).not.toHaveBeenCalled();
    expect(sC.sources.gelbooru).toEqual(beforeC);
  });

  it("set custom per_page 37 for stash_images accepted and PUT", async () => {
    const api = makeApi();
    const store = createViewSettings();
    await store.load(api);

    const result = await store.set("stash_images", { per_page: 37 });
    expect(result).toBe(true);
    expect(store.sources.stash_images.per_page).toBe(37);
    expect(api.putViewSetting).toHaveBeenCalledWith("stash_images", { mode: "grid", per_page: 37, zoom: 3 });
  });

  it("failed PUT keeps the local value and pushes the error toast", async () => {
    const api = makeApi({
      putViewSetting: vi.fn().mockRejectedValue(new Error("500")),
    });
    const store = createViewSettings();
    await store.load(api);

    const result = await store.set("danbooru", { zoom: 7 });
    expect(result).toBe(true);
    expect(store.sources.danbooru.zoom).toBe(7);
    expect(toasts.current?.message).toBe("Could not save view");
  });

  it("preview changes zoom without PUT", async () => {
    const api = makeApi();
    const store = createViewSettings();
    await store.load(api);

    store.preview("danbooru", { zoom: 8 });
    expect(store.sources.danbooru.zoom).toBe(8);
    expect(api.putViewSetting).not.toHaveBeenCalled();
  });

  it("get for unknown source returns placeholder", () => {
    const store = createViewSettings();
    const val = store.get("nonexistent_source");
    expect(val).toEqual(PLACEHOLDER);
  });

  it("load coerces mode to first allowed mode when server sends disallowed mode", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          stash_videos: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [60], per_page_max: 200, modes: ["wall", "list"] },
        },
      }),
    });
    const store = createViewSettings();
    await store.load(api);

    expect(store.sources.stash_videos.mode).toBe("wall");
  });

  it("load keeps allowed mode when server sends valid mode", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          komga_series: { mode: "list", per_page: 60, zoom: 3, per_page_options: [60], per_page_max: 200, modes: ["grid", "list"] },
        },
      }),
    });
    const store = createViewSettings();
    await store.load(api);

    expect(store.sources.komga_series.mode).toBe("list");
  });

  it("set rejects disallowed mode and accepts allowed mode", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          stash_videos: { mode: "wall", per_page: 60, zoom: 3, per_page_options: [60], per_page_max: 200, modes: ["wall", "list"] },
        },
      }),
    });
    const store = createViewSettings();
    await store.load(api);

    const r1 = await store.set("stash_videos", { mode: "grid" });
    expect(r1).toBe(false);
    expect(api.putViewSetting).not.toHaveBeenCalled();

    const r2 = await store.set("stash_videos", { mode: "list" });
    expect(r2).toBe(true);
    expect(api.putViewSetting).toHaveBeenCalledWith("stash_videos", { mode: "list", per_page: 60, zoom: 3 });
  });
});
