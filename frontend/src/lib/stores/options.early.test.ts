// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import type { Api, Options } from "../api/client";
import { createOptions } from "./options.svelte";

const base: Options = {
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
};

describe("options store: change before load", () => {
  it("is sent after load finishes and wins over the loaded value", async () => {
    vi.useFakeTimers();
    const api = {
      getOptions: vi.fn().mockResolvedValue(base),
      putOptions: vi.fn().mockResolvedValue({ ...base, sfw: true, sfw_set: true }),
    } as unknown as Api;
    const sfw = { set: vi.fn() };
    const store = createOptions({
      sfw,
      player: { loadRate: vi.fn() },
      storage: { getItem: () => null, removeItem: () => {} },
    });
    const loading = store.load(api);
    store.set({ sfw: true });
    await loading;
    await vi.advanceTimersByTimeAsync(400);
    expect(api.putOptions).toHaveBeenCalledWith({ sfw: true });
    expect(sfw.set).toHaveBeenLastCalledWith(true);
    vi.useRealTimers();
  });
});
