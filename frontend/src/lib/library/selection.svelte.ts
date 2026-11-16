import { errorText } from "../api/client";
import type { Api, LibraryItem } from "../api/client";
import { toasts } from "../stores/toasts.svelte";

export type Picked = { kind: LibraryItem["kind"]; id: string; title: string };

const UNDO_MS = 8000;

export function pickKey(item: { kind: string; id: string }): string {
  return `${item.kind}:${item.id}`;
}

export function createSelection() {
  let active = $state(false);
  let picked: Record<string, Picked> = $state({});
  let busy = $state(false);

  function toggle(item: LibraryItem) {
    active = true;
    const k = pickKey(item);
    if (picked[k]) delete picked[k];
    else picked[k] = { kind: item.kind, id: item.id, title: item.title };
  }

  function clear() {
    active = false;
    picked = {};
  }

  async function trashPicked(api: Api, onChanged: () => void): Promise<void> {
    const items = Object.values(picked).map((p) => ({ kind: p.kind, id: p.id }));
    if (items.length === 0 || busy) return;
    busy = true;
    try {
      const res = await api.trashItems(items);
      const moved = res.results.length;
      const failed = res.failed.length;
      clear();
      onChanged();
      if (moved === 0) {
        const unavailable = res.failed.some((f) => f.code === "trash_unavailable");
        toasts.push({
          kind: "error",
          message: unavailable
            ? "Could not move to Trash: Trash folder not available"
            : "Could not move to Trash. Try again.",
        });
        return;
      }
      const noun = moved === 1 ? "1 item" : `${moved} items`;
      toasts.push({
        kind: "undo",
        message: failed > 0 ? `Moved ${noun} to Trash, ${failed} failed` : `Moved ${noun} to Trash`,
        actionLabel: "Undo",
        durationMs: UNDO_MS,
        onAction: () => {
          api.restoreGroup(res.group).then(
            (r) => {
              onChanged();
              if (r.failed.length > 0) toasts.push({ kind: "error", message: `${r.failed.length} could not be restored` });
            },
            (e) => toasts.push({ kind: "error", message: errorText(e) }),
          );
        },
      });
    } catch (e) {
      toasts.push({ kind: "error", message: errorText(e) });
    } finally {
      busy = false;
    }
  }

  return {
    get active() { return active; },
    get busy() { return busy; },
    get count() { return Object.keys(picked).length; },
    has: (item: { kind: string; id: string }) => !!picked[pickKey(item)],
    toggle,
    clear,
    trashPicked,
  };
}

/** One selection shared by every library grid: a page change keeps it, leaving the page clears it. */
export const selection = createSelection();
