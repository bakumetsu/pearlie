import { describe, it, expect, vi, beforeEach, type Mock, type MockInstance } from "vitest";
import { createTrash } from "./trash.svelte";
import { toasts } from "./toasts.svelte";
import { ApiError } from "../api/client";
import type { Api } from "../api/client";

const sampleItem = {
  token: "tok1",
  expires_at: "2026-12-01T00:00:00Z",
  retention_days: 30,
  item: { kind: "image" as const, id: "img1", title: "My Photo" },
};

function makeApi(overrides: Partial<Record<string, Mock>> = {}) {
  return {
    listTrash: vi.fn().mockResolvedValue({ items: [], retention_days: 7 }),
    restore: vi.fn().mockResolvedValue(undefined),
    emptyTrash: vi.fn().mockResolvedValue({ removed: 0 }),
    ...overrides,
  } as unknown as Api & { listTrash: Mock; restore: Mock; emptyTrash: Mock };
}

describe("createTrash", () => {
  let pushSpy: MockInstance<typeof toasts.push>;

  beforeEach(() => {
    pushSpy = vi.spyOn(toasts, "push").mockImplementation(() => 0);
  });

  it("refresh fills items", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
    });
    const store = createTrash(api);
    await store.refresh();
    expect(api.listTrash).toHaveBeenCalledTimes(1);
    expect(store.items).toEqual([sampleItem]);
    expect(store.loaded).toBe(true);
    expect(store.offline).toBe(false);
  });

  it("refresh error sets offline+loaded", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockRejectedValue(new Error("network down")),
    });
    const store = createTrash(api);
    await store.refresh();
    expect(store.offline).toBe(true);
    expect(store.loaded).toBe(true);
    expect(store.items).toEqual([]);
  });

  it("restore success removes row, toasts info, calls onRestored", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
      restore: vi.fn().mockResolvedValue(undefined),
    });
    const onRestored = vi.fn();
    const store = createTrash(api, { onRestored });
    await store.refresh();
    await store.restore("tok1");
    expect(api.restore).toHaveBeenCalledWith("tok1");
    expect(store.items).toEqual([]);
    expect(pushSpy).toHaveBeenCalledWith({ kind: "info", message: "Restored: My Photo" });
    expect(onRestored).toHaveBeenCalledTimes(1);
  });

  it("restore 404 removes row with error toast and no onRestored", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
      restore: vi.fn().mockRejectedValue(new ApiError(404, "not_found", "gone")),
    });
    const onRestored = vi.fn();
    const store = createTrash(api, { onRestored });
    await store.refresh();
    await store.restore("tok1");
    expect(store.items).toEqual([]);
    expect(pushSpy).toHaveBeenCalledWith({ kind: "error", message: "Can't restore any more" });
    expect(onRestored).not.toHaveBeenCalled();
  });

  it("restore 500 keeps row", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
      restore: vi.fn().mockRejectedValue(new ApiError(500, "server_error", "server error")),
    });
    const store = createTrash(api);
    await store.refresh();
    await store.restore("tok1");
    expect(store.items).toEqual([sampleItem]);
    expect(pushSpy).toHaveBeenCalledWith({ kind: "error", message: "Could not restore. Try again." });
  });

  it("askEmpty with no items keeps confirming false", () => {
    const api = makeApi();
    const store = createTrash(api);
    store.askEmpty();
    expect(store.confirming).toBe(false);
  });

  it("askEmpty+cancelEmpty", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
    });
    const store = createTrash(api);
    await store.refresh();
    store.askEmpty();
    expect(store.confirming).toBe(true);
    store.cancelEmpty();
    expect(store.confirming).toBe(false);
  });

  it("confirmEmpty empties and toasts and resets confirming", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
      emptyTrash: vi.fn().mockResolvedValue({ removed: 3 }),
    });
    const store = createTrash(api);
    await store.refresh();
    store.askEmpty();
    expect(store.confirming).toBe(true);
    await store.confirmEmpty();
    expect(store.items).toEqual([]);
    expect(pushSpy).toHaveBeenCalledWith({ kind: "info", message: "Trash emptied: 3 items deleted for good" });
    expect(store.confirming).toBe(false);
  });

  it("keeps retentionDays from the list, also when empty", async () => {
    const store = createTrash(makeApi());
    expect(store.retentionDays).toBeNull();
    await store.refresh();
    expect(store.retentionDays).toBe(7);
  });

  it("confirmEmpty uses the singular for one item", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem], retention_days: 7 }),
      emptyTrash: vi.fn().mockResolvedValue({ removed: 1 }),
    });
    const store = createTrash(api);
    await store.refresh();
    store.askEmpty();
    await store.confirmEmpty();
    expect(pushSpy).toHaveBeenCalledWith({ kind: "info", message: "Trash emptied: 1 item deleted for good" });
  });

  it("confirmEmpty failure keeps items, error toast, confirming false", async () => {
    const api = makeApi({
      listTrash: vi.fn().mockResolvedValue({ items: [sampleItem] }),
      emptyTrash: vi.fn().mockRejectedValue(new Error("boom")),
    });
    const store = createTrash(api);
    await store.refresh();
    store.askEmpty();
    expect(store.confirming).toBe(true);
    await store.confirmEmpty();
    expect(store.items).toEqual([sampleItem]);
    expect(pushSpy).toHaveBeenCalledWith({ kind: "error", message: "Could not empty the trash. Try again." });
    expect(store.confirming).toBe(false);
  });
});
