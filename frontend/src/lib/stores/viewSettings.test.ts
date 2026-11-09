import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Api } from "../api/client";
import { toasts } from "./toasts.svelte";
import { createViewSettings, DEFAULTS } from "./viewSettings.svelte";

function makeApi(overrides: Partial<Record<string, unknown>> = {}): Api & Record<string, unknown> {
  const api: Record<string, unknown> = {
    getViewSettings: vi.fn().mockResolvedValue({ sources: {} }),
    putViewSetting: vi.fn().mockImplementation((_source: string, body: { mode: string; per_page: number; zoom: number }) =>
      Promise.resolve({ mode: body.mode, per_page: body.per_page, zoom: body.zoom, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 }),
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
    expect(store.sources.danbooru).toEqual(DEFAULTS.danbooru);
    expect(store.sources.stash_images).toEqual(DEFAULTS.stash_images);
    expect(store.sources.nhentai).toEqual(DEFAULTS.nhentai);
  });

  it("load merges server values and sets ready", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockResolvedValue({
        sources: {
          danbooru: { mode: "list", per_page: 40, zoom: 5, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
        },
      }),
    });
    const store = createViewSettings();
    await store.load(api);

    expect(store.ready).toBe(true);
    expect(store.sources.danbooru).toEqual({ mode: "list", per_page: 40, zoom: 5, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 });
    // Server omitted stash_images, so default is kept
    expect(store.sources.stash_images).toEqual(DEFAULTS.stash_images);
  });

  it("load failure keeps defaults and sets ready true without throwing", async () => {
    const api = makeApi({
      getViewSettings: vi.fn().mockRejectedValue(new Error("network down")),
    });
    const store = createViewSettings();
    await expect(store.load(api)).resolves.toBeUndefined();

    expect(store.ready).toBe(true);
    expect(store.sources.danbooru).toEqual(DEFAULTS.danbooru);
    expect(store.sources.stash_images).toEqual(DEFAULTS.stash_images);
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
    const api0 = makeApi();
    const s0 = createViewSettings();
    await s0.load(api0);
    const before0 = { ...s0.sources.gelbooru };
    const r0 = await s0.set("gelbooru", { per_page: 0 });
    expect(r0).toBe(false);
    expect(api0.putViewSetting).not.toHaveBeenCalled();
    expect(s0.sources.gelbooru).toEqual(before0);

    // per_page 61.5 (not a whole number)
    const apiF = makeApi();
    const sF = createViewSettings();
    await sF.load(apiF);
    const beforeF = { ...sF.sources.gelbooru };
    const rF = await sF.set("gelbooru", { per_page: 61.5 });
    expect(rF).toBe(false);
    expect(apiF.putViewSetting).not.toHaveBeenCalled();
    expect(sF.sources.gelbooru).toEqual(beforeF);

    // per_page 101 for gelbooru (cap is 100)
    const apiC = makeApi();
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

  it("get for unknown source returns danbooru defaults shape", () => {
    const store = createViewSettings();
    const val = store.get("nonexistent_source");
    expect(val).toEqual(DEFAULTS.danbooru);
  });
});
