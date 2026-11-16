import type { Api } from "../api/client";
import type { ToastsLike } from "./itemView.svelte";

export async function rejectTag(api: Api, toasts: ToastsLike, tag: string): Promise<void> {
  try {
    const { added } = await api.rejectTag(tag);

    if (!added) return;

    toasts.push({
      kind: "undo",
      message: "Rejected tag: " + tag,
      actionLabel: "Undo",
      onAction: async () => {
        try {
          await api.unrejectTag(tag);
        } catch {
          toasts.push({ kind: "error", message: "Can't undo any more" });
        }
      },
    });
  } catch {
    toasts.push({ kind: "error", message: "Could not reject the tag. Try again." });
  }
}
