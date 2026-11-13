// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Api, Options, OptionsUpdate } from "../api/client";

vi.mock("./toasts.svelte", () => ({
  toasts: { push: vi.fn() },
}));

import { toasts } from "./toasts.svelte";
import { createOptions } from "./options.svelte";

function makeOptions(overrides: Partial<Options> = {}): Options {
  return {
    sfw: false,
    sfw_set: false,
    player_rate: 1,
    player_rate_set: false,
    profile: "desktop",
    backdrop_strength: 60,
    backdrop_wall: true,
    backdrop_item: true,
    backdrop_lightbox: true,
    allow_blurred_tags: false,
    trash_retention_days: 7,
    infinite_scroll: false,
    hidden_sites: [],
    site_order: [],
    source_pace: { danbooru: { value: 1, default: 1, locked: false, backing_off: false } },
    ...overrides,
  };
}

describe("options store", () => {
  let api: Api;
  let storage: Pick<Storage, "getItem" | "removeItem">;
  let sfwDeps: { set: (on: boolean) => void };
  let playerDeps: { loadRate: (r: number) => void };
  let store: ReturnType<typeof createOptions>;
  let storageData: Record<string, string>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();

    storageData = {};
    api = { getOptions: vi.fn(), putOptions: vi.fn() } as unknown as Api;
    storage = {
      getItem: vi.fn((k: string) => storageData[k] ?? null),
      removeItem: vi.fn((k: string) => { delete storageData[k]; }),
    };
    sfwDeps = { set: vi.fn() };
    playerDeps = { loadRate: vi.fn() };
    store = createOptions({ sfw: sfwDeps, player: playerDeps, storage, debounceMs: 300 });
  });

  it("set source_pace merges optimistically and debounces PUT", async () => {
    const opts = makeOptions();
    vi.mocked(api.getOptions).mockResolvedValue(opts);
    vi.mocked(api.putOptions).mockResolvedValue(makeOptions());
    await store.load(api);

    store.set({ source_pace: { danbooru: 4 } } as OptionsUpdate);
    store.set({ source_pace: { danbooru: 5 } } as OptionsUpdate);

    expect(store.values?.source_pace.danbooru).toEqual({ value: 5, default: 1, locked: false, backing_off: false });

    await vi.advanceTimersByTimeAsync(300);

    expect(api.putOptions).toHaveBeenCalledTimes(1);
    expect(api.putOptions).toHaveBeenCalledWith({ source_pace: { danbooru: 5 } });
  });

  it("load applies values to deps and sets ready", async () => {
    const opts = makeOptions({ sfw: true, sfw_set: true, player_rate: 1.5, player_rate_set: true });
    vi.mocked(api.getOptions).mockResolvedValue(opts);

    await store.load(api);

    expect(store.ready).toBe(true);
    expect(store.values).toEqual(opts);
    expect(sfwDeps.set).toHaveBeenCalledWith(true);
    expect(playerDeps.loadRate).toHaveBeenCalledWith(1.5);
  });

  it("ready flag is false initially", () => {
    expect(store.ready).toBe(false);
    expect(store.values).toBeNull();
  });

  it("migration sends sfw+rate only when unset and removes keys", async () => {
    const opts = makeOptions({ sfw_set: false, player_rate_set: false });
    storageData["pearlie.sfw"] = "1";
    storageData["pearlie.player.rate"] = "1.5";

    vi.mocked(api.getOptions).mockResolvedValue(opts);
    const patched = makeOptions({ sfw: true, sfw_set: true, player_rate: 1.5, player_rate_set: true });
    vi.mocked(api.putOptions).mockResolvedValue(patched);

    await store.load(api);

    expect(api.putOptions).toHaveBeenCalledWith({ sfw: true, player_rate: 1.5 });
    expect(storage.removeItem).toHaveBeenCalledWith("pearlie.sfw");
    expect(storage.removeItem).toHaveBeenCalledWith("pearlie.player.rate");
    expect(store.values).toEqual(patched);
    expect(store.ready).toBe(true);
  });

  it("no PUT and keys removed when already set", async () => {
    const opts = makeOptions({ sfw: true, sfw_set: true, player_rate: 1, player_rate_set: true });
    storageData["pearlie.sfw"] = "0";
    storageData["pearlie.player.rate"] = "2";

    vi.mocked(api.getOptions).mockResolvedValue(opts);

    await store.load(api);

    expect(api.putOptions).not.toHaveBeenCalled();
    expect(storage.removeItem).toHaveBeenCalledWith("pearlie.sfw");
    expect(storage.removeItem).toHaveBeenCalledWith("pearlie.player.rate");
    expect(store.values).toEqual(opts);
  });

  it("failed migration PUT keeps keys", async () => {
    const opts = makeOptions({ sfw_set: false, player_rate_set: false });
    storageData["pearlie.sfw"] = "1";
    storageData["pearlie.player.rate"] = "1.25";

    vi.mocked(api.getOptions).mockResolvedValue(opts);
    vi.mocked(api.putOptions).mockRejectedValue(new Error("server error"));

    await store.load(api);

    expect(api.putOptions).toHaveBeenCalled();
    // Keys must NOT be removed because the PUT failed
    expect(storage.removeItem).not.toHaveBeenCalled();
    // Values fall back to the original GET result
    expect(store.values).toEqual(opts);
    expect(store.ready).toBe(true);
  });

  it("set is debounced into one PUT with merged patch", async () => {
    const opts = makeOptions({ sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true });
    vi.mocked(api.getOptions).mockResolvedValue(opts);
    await store.load(api);

    store.set({ sfw: true } as OptionsUpdate);
    store.set({ player_rate: 2 } as OptionsUpdate);

    // No PUT yet
    expect(api.putOptions).not.toHaveBeenCalled();

    const patched = makeOptions({ sfw: true, sfw_set: true, player_rate: 2, player_rate_set: true });
    vi.mocked(api.putOptions).mockResolvedValue(patched);

    await vi.advanceTimersByTimeAsync(300);

    expect(api.putOptions).toHaveBeenCalledTimes(1);
    expect(api.putOptions).toHaveBeenCalledWith({ sfw: true, player_rate: 2 });
    expect(store.values).toEqual(patched);
  });

  it("failure reverts values and toasts and re-applies to deps", async () => {
    const opts = makeOptions({ sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true });
    vi.mocked(api.getOptions).mockResolvedValue(opts);
    await store.load(api);

    vi.mocked(api.putOptions).mockRejectedValue(new Error("fail"));

    store.set({ sfw: true } as OptionsUpdate);

    // Optimistic state is visible immediately
    expect(store.values?.sfw).toBe(true);
    expect(sfwDeps.set).toHaveBeenLastCalledWith(true);

    await vi.advanceTimersByTimeAsync(300);

    // Reverted
    expect(store.values?.sfw).toBe(false);
    expect(sfwDeps.set).toHaveBeenLastCalledWith(false);
    expect(playerDeps.loadRate).toHaveBeenLastCalledWith(1);
    expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Could not save options" });
  });

  it("invalid stored rate (99) is ignored", async () => {
    const opts = makeOptions({ sfw_set: false, player_rate_set: false });
    storageData["pearlie.sfw"] = "1";
    storageData["pearlie.player.rate"] = "99";

    vi.mocked(api.getOptions).mockResolvedValue(opts);
    const patched = makeOptions({ sfw: true, sfw_set: true, player_rate: 1, player_rate_set: false });
    vi.mocked(api.putOptions).mockResolvedValue(patched);

    await store.load(api);

    // Only sfw was valid; rate 99 is not in the allowed list
    expect(api.putOptions).toHaveBeenCalledWith({ sfw: true });
    // sfw key removed (migrated), rate key NOT removed
    expect(storage.removeItem).toHaveBeenCalledWith("pearlie.sfw");
    expect(storage.removeItem).not.toHaveBeenCalledWith("pearlie.player.rate");
  });
});
