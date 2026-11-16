import { ApiError, isOffline, errorText } from "../api/client";
import type { Api, TrashResult } from "../api/client";
import { toasts } from "./toasts.svelte";

export type Trash = ReturnType<typeof createTrash>;

export type TrashGroup = { group: string | null; items: TrashResult[] };

/** Group rows by group_id, keeping list order; rows without a group stay single. */
export function groupRows(rows: TrashResult[]): TrashGroup[] {
  const out: TrashGroup[] = [];
  const at = new Map<string, TrashGroup>();
  for (const r of rows) {
    const g = r.item.group_id ?? null;
    if (g === null) { out.push({ group: null, items: [r] }); continue; }
    let slot = at.get(g);
    if (!slot) { slot = { group: g, items: [] }; at.set(g, slot); out.push(slot); }
    slot.items.push(r);
  }
  return out;
}

export function createTrash(api: Api, opts?: { onRestored?: () => void }) {
  let items: TrashResult[] = $state([]);
  let loaded = $state(false);
  let offline = $state(false);
  let error: string | null = $state(null);
  let confirming = $state(false);
  let retentionDays: number | null = $state(null);
  let confirmingToken: string | null = $state(null);

  async function refresh(): Promise<void> {
    try {
      const res = await api.listTrash();
      items = res.items;
      retentionDays = res.retention_days;
      offline = false;
      error = null;
      loaded = true;
    } catch (e) {
      if (isOffline(e)) { offline = true; error = null; } else { offline = false; error = errorText(e); }
      loaded = true;
    }
  }

  async function restore(token: string): Promise<void> {
    const idx = items.findIndex((t) => t.token === token);
    if (idx === -1) return;
    const entry = items[idx];
    try {
      await api.restore(token);
      items = items.filter((t) => t.token !== token);
      toasts.push({ kind: "info", message: `Restored: ${entry.item.title}` });
      opts?.onRestored?.();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        items = items.filter((t) => t.token !== token);
        toasts.push({ kind: "error", message: "Can't restore any more" });
      } else {
        toasts.push({ kind: "error", message: "Could not restore. Try again." });
      }
    }
  }

  async function restoreGroup(group: string): Promise<void> {
    try {
      const r = await api.restoreGroup(group);
      const back = new Set(r.restored.map((x) => `${x.item.kind}:${x.item.id}`));
      items = items.filter((t) => t.item.group_id !== group || !back.has(`${t.item.kind}:${t.item.id}`));
      if (r.failed.length > 0) {
        await refresh();
        toasts.push({ kind: "error", message: `${r.failed.length} could not be restored` });
      } else {
        toasts.push({ kind: "info", message: `Restored ${r.restored.length} ${r.restored.length === 1 ? "item" : "items"}` });
      }
      opts?.onRestored?.();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        await refresh();
        toasts.push({ kind: "error", message: "Can't restore any more" });
      } else {
        toasts.push({ kind: "error", message: "Could not restore. Try again." });
      }
    }
  }

  function askDelete(token: string): void {
    confirmingToken = token;
  }

  function cancelDelete(): void {
    confirmingToken = null;
  }

  async function confirmDelete(): Promise<void> {
    const token = confirmingToken;
    if (token === null) return;
    const entry = items.find((t) => t.token === token);
    try {
      await api.deleteForGood(token);
      items = items.filter((t) => t.token !== token);
      toasts.push({ kind: "info", message: `Deleted for good: ${entry?.item.title ?? "item"}` });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        items = items.filter((t) => t.token !== token);
      } else {
        toasts.push({ kind: "error", message: "Could not delete. Try again." });
      }
    } finally {
      confirmingToken = null;
    }
  }

  function askEmpty(): void {
    confirming = items.length > 0;
  }

  function cancelEmpty(): void {
    confirming = false;
  }

  async function confirmEmpty(): Promise<void> {
    if (!confirming) return;
    try {
      const r = await api.emptyTrash();
      items = [];
      toasts.push({ kind: "info", message: `Trash emptied: ${r.removed} ${r.removed === 1 ? "item" : "items"} deleted for good` });
    } catch {
      toasts.push({ kind: "error", message: "Could not empty the trash. Try again." });
    } finally {
      confirming = false;
    }
  }

  return {
    get items() { return items; },
    get loaded() { return loaded; },
    get offline() { return offline; },
    get error() { return error; },
    get confirming() { return confirming; },
    get retentionDays() { return retentionDays; },
    get confirmingToken() { return confirmingToken; },
    get groups() { return groupRows(items); },
    get totalBytes() { return items.reduce((a, t) => a + (t.item.size_bytes ?? 0), 0); },
    restoreGroup,
    askDelete,
    cancelDelete,
    confirmDelete,
    refresh,
    restore,
    askEmpty,
    cancelEmpty,
    confirmEmpty,
  };
}
