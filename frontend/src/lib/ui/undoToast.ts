import { toasts } from "$lib/stores/toasts.svelte";

/** Library deletes show this: message plus Undo, open for 8 s (paused on hover and focus). */
export function undoToast(message: string, onundo: () => void): number {
  return toasts.push({ kind: "undo", message, actionLabel: "Undo", onAction: onundo, durationMs: 8000 });
}
