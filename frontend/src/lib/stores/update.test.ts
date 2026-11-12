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
