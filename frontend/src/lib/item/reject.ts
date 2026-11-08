import type { Api } from "../api/client";
import type { ToastsLike } from "./itemView.svelte";

export async function rejectTag(api: Api, toasts: ToastsLike, tag: string): Promise<void> {
  try {
    const rules = await api.getRules();
    const reject = rules.reject ?? [];

    if (reject.includes(tag)) return;

    await api.putRules({
      version: rules.version,
      reject: [...reject, tag],
      warn: rules.warn,
      require: rules.require,
      mapping: rules.mapping,
    });

    toasts.push({
      kind: "undo",
      message: "Rejected tag: " + tag,
      actionLabel: "Undo",
      onAction: async () => {
        try {
          const r = await api.getRules();
          await api.putRules({
            version: r.version,
            reject: (r.reject ?? []).filter((t) => t !== tag),
            warn: r.warn,
            require: r.require,
            mapping: r.mapping,
          });
        } catch {
          toasts.push({ kind: "error", message: "Can't undo any more" });
        }
      },
    });
  } catch {
    toasts.push({ kind: "error", message: "Could not reject the tag. Try again." });
  }
}
