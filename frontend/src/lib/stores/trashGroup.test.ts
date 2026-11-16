import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { createTrash, groupRows } from "./trash.svelte";
import { toasts } from "./toasts.svelte";
import { ApiError } from "../api/client";
import type { Api } from "../api/client";

function row(token: string, id: string, group: string | null) {
  return {
    token,
    expires_at: "2026-12-01T00:00:00Z",
    retention_days: 7,
    item: { kind: "image" as const, id, title: `T ${id}`, group_id: group },
  };
}

function makeApi(items: ReturnType<typeof row>[], over: Partial<Record<string, Mock>> = {}) {
  return {
    listTrash: vi.fn().mockResolvedValue({ items, retention_days: 7 }),
    restoreGroup: vi.fn(),
    deleteForGood: vi.fn().mockResolvedValue(undefined),
    ...over,
  } as unknown as Api & { restoreGroup: Mock; deleteForGood: Mock };
}

describe("trash groups", () => {
  beforeEach(() => {
    vi.spyOn(toasts, "push").mockImplementation(() => 0);
  });

  it("groupRows keeps order and leaves ungrouped rows single", () => {
    const g = groupRows([row("a", "1", "G"), row("b", "2", null), row("c", "3", "G")]);
    expect(g.map((x) => x.items.map((i) => i.token))).toEqual([["a", "c"], ["b"]]);
  });

  it("restoreGroup removes the restored rows", async () => {
    const items = [row("a", "1", "G"), row("b", "2", "G"), row("c", "3", null)];
    const api = makeApi(items);
    api.restoreGroup.mockResolvedValue({
      restored: [{ item: { kind: "image", id: "1" } }, { item: { kind: "image", id: "2" } }],
      failed: [],
    });
    const onRestored = vi.fn();
    const store = createTrash(api, { onRestored });
    await store.refresh();
    await store.restoreGroup("G");
    expect(store.items.map((t) => t.token)).toEqual(["c"]);
    expect(onRestored).toHaveBeenCalled();
  });

  it("restoreGroup 404 reloads the list and shows an error", async () => {
    const api = makeApi([row("c", "3", null)]);
    api.restoreGroup.mockRejectedValue(new ApiError(404, "not_found", "x"));
    const store = createTrash(api);
    await store.restoreGroup("G");
    expect(api.listTrash).toHaveBeenCalled();
    expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Can't restore any more" });
  });

  it("delete for good asks first, then removes the row", async () => {
    const api = makeApi([row("a", "1", null), row("b", "2", null)]);
    const store = createTrash(api);
    await store.refresh();
    store.askDelete("a");
    expect(store.confirmingToken).toBe("a");
    expect(api.deleteForGood).not.toHaveBeenCalled();
    await store.confirmDelete();
    expect(api.deleteForGood).toHaveBeenCalledWith("a");
    expect(store.items.map((t) => t.token)).toEqual(["b"]);
    expect(store.confirmingToken).toBeNull();
  });

  it("cancelDelete keeps the row", async () => {
    const api = makeApi([row("a", "1", null)]);
    const store = createTrash(api);
    await store.refresh();
    store.askDelete("a");
    store.cancelDelete();
    await store.confirmDelete();
    expect(api.deleteForGood).not.toHaveBeenCalled();
    expect(store.items).toHaveLength(1);
  });
});
