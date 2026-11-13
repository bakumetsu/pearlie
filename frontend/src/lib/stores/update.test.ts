// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError } from "../api/client";
import type { Api, UpdateStatus } from "../api/client";
import { createUpdate } from "./update.svelte";
import { toasts } from "./toasts.svelte";

vi.mock("./toasts.svelte", () => ({ toasts: { push: vi.fn() } }));

function makeStatus(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    installed: { version: "1.0.0", channel: "main", commit: "abc123" },
    latest: null,
    available: false,
    checked_at: "2026-01-01T00:00:00Z",
    check_enabled: true,
    channel: "main",
    state: "idle",
    step: null,
    error: null,
    retry_after: null,
    can_apply: false,
    ...overrides,
  };
}

describe("createUpdate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("load sets status", async () => {
    const s = makeStatus({ latest: { version: "2.0.0", url: "https://example.test/r", commit: "def456" }, available: true });
    const api = {
      getUpdateStatus: vi.fn().mockResolvedValue(s),
      putUpdateSettings: vi.fn().mockResolvedValue(s),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    expect(store.status).toEqual(s);
    expect(store.loaded).toBe(true);
    expect(store.offline).toBe(false);
  });

  it("a failed load retries on its own and recovers; Restarting shows while health fails", async () => {
    const s = makeStatus();
    const api = {
      getUpdateStatus: vi.fn().mockRejectedValueOnce(new ApiError(403, "forbidden", "Forbidden")).mockResolvedValue(s),
      health: vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValue({ status: "ok" }),
    } as unknown as Api;

    const store = createUpdate(api, { retryMs: 10 });
    await store.load();
    expect(store.status).toBeNull();
    expect(store.error).not.toBeNull();
    expect(store.phase).toBe("restarting");
    await vi.waitFor(() => expect(store.status).toEqual(s));
    expect(store.error).toBeNull();
    expect(store.phase).toBe("idle");
    store.dispose();
  });

  it("retry() reloads at once and stops the timer on success", async () => {
    const s = makeStatus();
    const api = {
      getUpdateStatus: vi.fn().mockRejectedValueOnce(new ApiError(500, "boom", "Boom")).mockResolvedValue(s),
      health: vi.fn().mockResolvedValue({ status: "ok" }),
    } as unknown as Api;

    const store = createUpdate(api, { retryMs: 60_000 });
    await store.load();
    expect(store.status).toBeNull();
    await store.retry();
    expect(store.status).toEqual(s);
    expect(store.phase).toBe("idle");
    store.dispose();
  });

  it("lastLatest survives a later status with latest null + error rate_limited", async () => {
    const first = makeStatus({ latest: { version: "2.0.0", url: "https://example.test/r", commit: "def456" }, available: true });
    const second = makeStatus({ latest: null, available: false, error: "rate_limited" });

    let call = 0;
    const api = {
      getUpdateStatus: vi.fn().mockImplementation(() => {
        call++;
        return Promise.resolve(call === 1 ? first : second);
      }),
      putUpdateSettings: vi.fn().mockResolvedValue(first),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    expect(store.latest).toEqual({ version: "2.0.0", url: "https://example.test/r", commit: "def456" });

    await store.load(true);
    expect(store.status?.latest).toBeNull();
    expect(store.latestState).toBe("check_later");
    expect(store.latest).toEqual({ version: "2.0.0", url: "https://example.test/r", commit: "def456" });
  });

  it("unreachable", async () => {
    const s = makeStatus({ error: "unreachable" });
    const api = {
      getUpdateStatus: vi.fn().mockResolvedValue(s),
      putUpdateSettings: vi.fn().mockResolvedValue(s),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    expect(store.latestState).toBe("unreachable");
  });

  it("checkNow passes {refresh:true, manual:true}", async () => {
    const s = makeStatus();
    const api = {
      getUpdateStatus: vi.fn().mockResolvedValue(s),
      putUpdateSettings: vi.fn().mockResolvedValue(s),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.checkNow();
    expect(api.getUpdateStatus).toHaveBeenCalledWith({ refresh: true, manual: true });
  });

  it("setChannel calls PUT then a manual check", async () => {
    const initial = makeStatus({ channel: "main" });
    const putResult = makeStatus({ channel: "dev" });
    const checkResult = makeStatus({ channel: "dev" });

    const api = {
      getUpdateStatus: vi.fn()
        .mockResolvedValueOnce(initial)
        .mockResolvedValueOnce(checkResult),
      putUpdateSettings: vi.fn().mockResolvedValue(putResult),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    await store.setChannel("dev");

    expect(api.putUpdateSettings).toHaveBeenCalledWith({ channel: "dev" });
    expect(api.getUpdateStatus).toHaveBeenLastCalledWith({ refresh: true, manual: true });
  });

  it("setChannel is a no-op for the same channel", async () => {
    const s = makeStatus({ channel: "main" });
    const api = {
      getUpdateStatus: vi.fn().mockResolvedValue(s),
      putUpdateSettings: vi.fn().mockResolvedValue(s),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    await store.setChannel("main");
    expect(api.putUpdateSettings).not.toHaveBeenCalled();
  });

  it("setChannel failure keeps old status and toasts", async () => {
    const old = makeStatus({ channel: "main" });
    const api = {
      getUpdateStatus: vi.fn().mockResolvedValue(old),
      putUpdateSettings: vi.fn().mockRejectedValue(new ApiError(500, "server", "oops")),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    await store.setChannel("dev");

    expect(store.status?.channel).toBe("main");
    expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Could not switch channel. Try again." });
  });

  it("setCheckEnabled", async () => {
    const s = makeStatus({ check_enabled: true });
    const result = makeStatus({ check_enabled: false });
    const api = {
      getUpdateStatus: vi.fn().mockResolvedValue(s),
      putUpdateSettings: vi.fn().mockResolvedValue(result),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    await store.setCheckEnabled(false);

    expect(api.putUpdateSettings).toHaveBeenCalledWith({ check_enabled: false });
    expect(store.status?.check_enabled).toBe(false);
  });

  it("apply success then poll", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi
        .fn()
        .mockResolvedValueOnce(makeStatus({ state: "running", step: "Building" }))
        .mockResolvedValueOnce(
          makeStatus({ state: "done", installed: { version: "2.0.0", channel: "main", commit: "x" } })
        );
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      expect(store.phase).toBe("running");

      await vi.advanceTimersByTimeAsync(15);
      expect(store.step).toBe("Building");

      await vi.advanceTimersByTimeAsync(15);
      expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Updated to 2.0.0" });
      expect(reload).toHaveBeenCalledTimes(1);
      expect(store.phase).toBe("idle");
    } finally {
      vi.useRealTimers();
    }
  });

  it("cap: status stays running, gives up after maxMs", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi.fn().mockResolvedValue(makeStatus({ state: "running", step: "Building" }));
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, maxMs: 100, reload });

      await store.apply();
      await vi.advanceTimersByTimeAsync(200);
      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Update did not finish. Check /opt/pearlie/update.log.",
      });
      expect(store.phase).toBe("idle");
      expect(reload).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("done saves the notice and the next load shows it once", async () => {
    vi.useFakeTimers();
    try {
      sessionStorage.clear();
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi
        .fn()
        .mockResolvedValueOnce(
          makeStatus({ state: "done", installed: { version: "2.0.0", channel: "main", commit: "x" } })
        )
        .mockResolvedValue(makeStatus());
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      await vi.advanceTimersByTimeAsync(15);
      expect(reload).toHaveBeenCalledTimes(1);
      expect(sessionStorage.getItem("pearlie.update.notice")).toBe("Updated to 2.0.0");

      vi.clearAllMocks();
      const store2 = createUpdate(api, { reload });
      await store2.load();
      expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Updated to 2.0.0" });
      expect(toasts.push).toHaveBeenCalledTimes(1);
      expect(sessionStorage.getItem("pearlie.update.notice")).toBeNull();
      await store2.load();
      expect(toasts.push).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("available wins over retry_after", async () => {
    const getUpdateStatus = vi.fn().mockResolvedValue(
      makeStatus({ available: true, retry_after: 30, latest: { version: "1.2.4", url: "u" } as UpdateStatus["latest"] })
    );
    const api = { getUpdateStatus } as unknown as Api;
    const store = createUpdate(api);
    await store.load();
    expect(store.latestState).toBe("available");
  });

  it("restart tolerance: health rejects twice then recovers to done", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi
        .fn()
        .mockRejectedValueOnce(new Error("502"))
        .mockRejectedValueOnce(new Error("502"))
        .mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi.fn().mockResolvedValue(
        makeStatus({ state: "done", installed: { version: "2.0.0", channel: "main", commit: "x" } })
      );
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();

      await vi.advanceTimersByTimeAsync(15);
      expect(store.phase).toBe("restarting");

      await vi.advanceTimersByTimeAsync(10);
      expect(store.phase).toBe("restarting");

      await vi.advanceTimersByTimeAsync(15);
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("rolled_back: error toast, applyError set, no reload, phase idle", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi
        .fn()
        .mockResolvedValue(makeStatus({ state: "rolled_back", error: "boom" }));
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      await vi.advanceTimersByTimeAsync(15);

      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Update failed and was rolled back: boom",
      });
      expect(reload).not.toHaveBeenCalled();
      expect(store.applyError).toBe("boom");
      expect(store.phase).toBe("idle");
    } finally {
      vi.useRealTimers();
    }
  });

  it("failed_rollback: phase set, applyError set, no toast, no reload", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi
        .fn()
        .mockResolvedValue(makeStatus({ state: "failed_rollback", error: "disk full" }));
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      await vi.advanceTimersByTimeAsync(15);

      expect(store.phase).toBe("failed_rollback");
      expect(store.applyError).toBe("disk full");
      expect(toasts.push).not.toHaveBeenCalled();
      expect(reload).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("timeout: health never recovers, error toast after 200 ms", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
      const health = vi.fn().mockRejectedValue(new Error("down"));
      const getUpdateStatus = vi.fn();
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      await vi.advanceTimersByTimeAsync(200);

      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Pearlie did not come back. Check the console.",
      });
      expect(store.phase).toBe("idle");
    } finally {
      vi.useRealTimers();
    }
  });

  it("apply 409 already_running: phase becomes running", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockRejectedValue(new ApiError(409, "already_running", "x"));
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi.fn().mockResolvedValue(
        makeStatus({ state: "done", installed: { version: "2.0.0", channel: "main", commit: "x" } })
      );
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      expect(store.phase).toBe("running");
    } finally {
      vi.useRealTimers();
    }
  });

  it("apply 409 up_to_date: info toast, phase stays idle", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockRejectedValue(new ApiError(409, "up_to_date", "x"));
      const health = vi.fn();
      const getUpdateStatus = vi.fn();
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Already up to date." });
      expect(store.phase).toBe("idle");
    } finally {
      vi.useRealTimers();
    }
  });

  it("apply 503: error toast 'Updating is not available here.'", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn().mockRejectedValue(new ApiError(503, "unavailable", "x"));
      const health = vi.fn();
      const getUpdateStatus = vi.fn();
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.apply();
      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Updating is not available here.",
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it("resume() starts polling after load(); dispose() stops it", async () => {
    vi.useFakeTimers();
    try {
      const applyUpdate = vi.fn();
      const health = vi.fn().mockResolvedValue({ status: "ok" });
      const getUpdateStatus = vi
        .fn()
        .mockResolvedValueOnce(makeStatus({ state: "running", step: "Installing" }));
      const putUpdateSettings = vi.fn();
      const reload = vi.fn();
      const api = { applyUpdate, health, getUpdateStatus, putUpdateSettings } as unknown as Api;
      const store = createUpdate(api, { intervalMs: 10, timeoutMs: 100, reload });

      await store.load();
      store.resume();
      expect(store.phase).toBe("running");

      await vi.advanceTimersByTimeAsync(15);
      const callsAfterPoll = health.mock.calls.length;
      expect(callsAfterPoll).toBeGreaterThan(0);

      store.dispose();
      await vi.advanceTimersByTimeAsync(50);
      expect(health.mock.calls.length).toBe(callsAfterPoll);
    } finally {
      vi.useRealTimers();
    }
  });

  it("offline on network ApiError(0,'network',…)", async () => {
    const api = {
      getUpdateStatus: vi.fn().mockRejectedValue(new ApiError(0, "network", "connection failed")),
      putUpdateSettings: vi.fn().mockResolvedValue(makeStatus()),
    } as unknown as Api;

    const store = createUpdate(api);
    await store.load();
    expect(store.offline).toBe(true);
    expect(store.loaded).toBe(true);
  });
});
