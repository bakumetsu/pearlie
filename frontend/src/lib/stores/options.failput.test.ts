// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Api, Options } from "../api/client";
vi.mock("./toasts.svelte", () => ({ toasts: { push: vi.fn() } }));
import { toasts } from "./toasts.svelte";
import { createOptions } from "./options.svelte";

function makeOptions(overrides: Partial<Options> = {}): Options {
  return {
    sfw: false,
    sfw_set: true,
    player_rate: 1,
    player_rate_set: true,
    profile: "desktop",
    backdrop_strength: 60,
    backdrop_wall: true,
    backdrop_item: true,
    backdrop_lightbox: true,
    allow_blurred_tags: false,
    trash_retention_days: 7,
    images_per_site: 10,
    infinite_scroll: false,
    place_mode: "suggest",
    hidden_sites: [],
    site_order: [],
    thumb_cache: { max_mb: 1024, used_mb: 0, files: 0, available: true },
    source_pace: {},
    ...overrides,
  };
}

describe("options failput", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  it("keeps pendingPatch across failed PUT and re-flushes", async () => {
    const storage = { getItem: vi.fn(() => null), removeItem: vi.fn() };
    const loaded = makeOptions();
    const received: Record<string, unknown>[] = [];
    let callCount = 0;

    const api = {
      getOptions: vi.fn().mockResolvedValue(loaded),
      putOptions: vi.fn((patch: Record<string, unknown>) => {
        callCount++;
        if (callCount === 1) {
          return new Promise<never>((_, reject) => {
            setTimeout(() => reject(new Error("x")), 500);
          });
        }
        received.push(patch);
        return Promise.resolve({ ...loaded, ...patch });
      }),
    } as unknown as Api;

    const store = createOptions({
      sfw: { set: vi.fn() },
      player: { loadRate: vi.fn() },
      storage,
      debounceMs: 300,
    });

    await store.load(api);
    expect(store.values?.backdrop_wall).toBe(true);
    expect(store.values?.backdrop_item).toBe(true);

    store.set({ backdrop_wall: false });
    await vi.advanceTimersByTimeAsync(300); // debounce fires → PUT in flight

    store.set({ backdrop_item: false }); // goes into pendingPatch
    await vi.advanceTimersByTimeAsync(500); // first PUT rejects

    expect(toasts.push).toHaveBeenCalledTimes(1);
    expect(store.values?.backdrop_wall).toBe(true);
    expect(store.values?.backdrop_item).toBe(false);

    await vi.advanceTimersByTimeAsync(3000); // re-flush PUT resolves

    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({ backdrop_item: false });
    expect(store.values?.backdrop_item).toBe(false);
  });

  it("reverts to loaded values on failed PUT with nothing pending", async () => {
    const storage = { getItem: vi.fn(() => null), removeItem: vi.fn() };
    const loaded = makeOptions();

    const api = {
      getOptions: vi.fn().mockResolvedValue(loaded),
      putOptions: vi.fn(() =>
        new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error("x")), 500);
        }),
      ),
    } as unknown as Api;

    const store = createOptions({
      sfw: { set: vi.fn() },
      player: { loadRate: vi.fn() },
      storage,
      debounceMs: 300,
    });

    await store.load(api);
    store.set({ backdrop_wall: false });

    await vi.advanceTimersByTimeAsync(300); // debounce fires → PUT in flight
    await vi.advanceTimersByTimeAsync(500); // PUT rejects

    expect(toasts.push).toHaveBeenCalledTimes(1);
    expect(store.values?.backdrop_wall).toBe(true);
    expect(store.values?.backdrop_item).toBe(true);
  });
});
