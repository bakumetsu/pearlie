// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import type { Api, Options } from "../api/client";
import { createOptions } from "./options.svelte";
import { toasts } from "./toasts.svelte";

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
  source_pace: {},
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

describe("options store: load failure", () => {
  const mk = (_api: Api) =>
    createOptions({
      sfw: { set: vi.fn() },
      player: { loadRate: vi.fn() },
      storage: { getItem: () => null, removeItem: () => {} },
    });

  it("a toggle after a failed load retries the load and is then saved", async () => {
    vi.useFakeTimers();
    const api = {
      getOptions: vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValue(base),
      putOptions: vi.fn().mockResolvedValue({ ...base, sfw: true, sfw_set: true }),
    } as unknown as Api;
    const store = mk(api);
    await store.load(api);
    expect(store.values).toBeNull();
    store.set({ sfw: true });
    await vi.advanceTimersByTimeAsync(400);
    expect(api.getOptions).toHaveBeenCalledTimes(2);
    expect(api.putOptions).toHaveBeenCalledWith({ sfw: true });
    vi.useRealTimers();
  });

  it("a toggle when the retry also fails shows an error toast", async () => {
    vi.useFakeTimers();
    const push = vi.spyOn(toasts, "push");
    const api = {
      getOptions: vi.fn().mockRejectedValue(new Error("down")),
      putOptions: vi.fn(),
    } as unknown as Api;
    const store = mk(api);
    await store.load(api);
    store.set({ sfw: true });
    await vi.advanceTimersByTimeAsync(400);
    expect(api.putOptions).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith({ kind: "error", message: "Could not save options" });
    push.mockRestore();
    vi.useRealTimers();
  });

  it("a toggle queued during a failing first load shows an error toast", async () => {
    const push = vi.spyOn(toasts, "push");
    const api = {
      getOptions: vi.fn().mockRejectedValue(new Error("down")),
      putOptions: vi.fn(),
    } as unknown as Api;
    const store = mk(api);
    const loading = store.load(api);
    store.set({ sfw: true });
    await loading;
    expect(push).toHaveBeenCalledWith({ kind: "error", message: "Could not save options" });
    push.mockRestore();
  });
});
