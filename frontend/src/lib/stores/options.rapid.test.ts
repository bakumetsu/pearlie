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
    hidden_sites: [],
    site_order: [],
    source_pace: {},
    ...overrides,
  };
}

describe("options store rapid changes", () => {
  let api: Api;
  let server: Options;
  let received: OptionsUpdate[];
  let store: ReturnType<typeof createOptions>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    server = makeOptions();
    received = [];
    api = {
      getOptions: vi.fn(async () => server),
      // Slow PUT: the reply is a snapshot of the server at request time
      putOptions: vi.fn(async (patch: OptionsUpdate) => {
        received.push(patch);
        server = { ...server, ...(patch as Partial<Options>) };
        const snapshot = server;
        await new Promise((r) => setTimeout(r, 500));
        return snapshot;
      }),
    } as unknown as Api;
    const storage = { getItem: vi.fn(() => null), removeItem: vi.fn() };
    store = createOptions({
      sfw: { set: vi.fn() },
      player: { loadRate: vi.fn() },
      storage,
      debounceMs: 300,
    });
  });

  it("one switch toggled on then off ends off and the server gets off", async () => {
    await store.load(api);
    store.set({ backdrop_wall: false });
    await vi.advanceTimersByTimeAsync(300); // first PUT (off) in flight
    store.set({ backdrop_wall: true });
    expect(store.values?.backdrop_wall).toBe(true);
    await vi.advanceTimersByTimeAsync(500); // reply for the first PUT arrives
    expect(store.values?.backdrop_wall).toBe(true); // reply must not flip it back
    store.set({ backdrop_wall: false });
    await vi.advanceTimersByTimeAsync(3000);
    expect(store.values?.backdrop_wall).toBe(false);
    expect(server.backdrop_wall).toBe(false);
  });

  it("two switches toggled within 1 s both stay and both reach the server", async () => {
    await store.load(api);
    store.set({ backdrop_wall: false });
    await vi.advanceTimersByTimeAsync(300);
    store.set({ backdrop_item: false }); // while the first PUT is in flight
    await vi.advanceTimersByTimeAsync(500); // first reply arrives
    expect(store.values?.backdrop_wall).toBe(false);
    expect(store.values?.backdrop_item).toBe(false);
    await vi.advanceTimersByTimeAsync(3000);
    expect(store.values?.backdrop_wall).toBe(false);
    expect(store.values?.backdrop_item).toBe(false);
    expect(server.backdrop_wall).toBe(false);
    expect(server.backdrop_item).toBe(false);
  });

  it("never has two PUTs in flight at once", async () => {
    let active = 0;
    let maxActive = 0;
    vi.mocked(api.putOptions).mockImplementation(async (patch: OptionsUpdate) => {
      active++;
      maxActive = Math.max(maxActive, active);
      received.push(patch);
      await new Promise((r) => setTimeout(r, 1000));
      active--;
      return makeOptions();
    });
    await store.load(api);
    store.set({ backdrop_wall: false });
    await vi.advanceTimersByTimeAsync(300);
    store.set({ backdrop_item: false });
    await vi.advanceTimersByTimeAsync(400); // debounce fires while PUT 1 is in flight
    expect(maxActive).toBe(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(maxActive).toBe(1);
    expect(received).toEqual([{ backdrop_wall: false }, { backdrop_item: false }]);
  });

  it("a PUT failure still rolls back and toasts", async () => {
    vi.mocked(api.putOptions).mockRejectedValue(new Error("boom"));
    await store.load(api);
    store.set({ backdrop_wall: false });
    expect(store.values?.backdrop_wall).toBe(false);
    await vi.advanceTimersByTimeAsync(300);
    expect(store.values?.backdrop_wall).toBe(true);
    expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Could not save options" });
  });
});
