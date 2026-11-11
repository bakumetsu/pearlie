import { ApiError, isOffline, errorText } from "../api/client";
import type { Api, TrashResult } from "../api/client";
import { toasts } from "./toasts.svelte";

export type Trash = ReturnType<typeof createTrash>;

export function createTrash(api: Api, opts?: { onRestored?: () => void }) {
  let items: TrashResult[] = $state([]);
  let loaded = $state(false);
  let offline = $state(false);
  let error: string | null = $state(null);
  let confirming = $state(false);
  let retentionDays: number | null = $state(null);

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
    refresh,
    restore,
    askEmpty,
    cancelEmpty,
    confirmEmpty,
  };
}
