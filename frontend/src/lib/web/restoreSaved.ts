import { errorText } from "../api/client";
import type { Api } from "../api/client";
import { itemHref } from "../item/kinds";

type Toast = { kind: "info" | "error"; message: string };

// Restore from the "already saved, in the Trash" toast; the item comes back under a new id, so open it there.
export function restoreSaved(deps: { api: Api; navigate: (href: string) => void; toast: (t: Toast) => void }) {
  return (token: string): void => {
    deps.api.restore(token).then(
      (r) => {
        deps.toast({ kind: "info", message: "Restored from the Trash" });
        deps.navigate(itemHref({ kind: r.item.kind, id: r.item.id }));
      },
      (e) => deps.toast({ kind: "error", message: errorText(e) }),
    );
  };
}
