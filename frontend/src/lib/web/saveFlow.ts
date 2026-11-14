import type { WebItem } from "../api/client";
import { toPlural } from "../item/kinds";
import type { PlacementAnswer } from "../stores/placement.svelte";

export type SaveResult =
  | { result: "queued" }
  | { result: "in_library"; ref?: { kind: string; id: string } }
  | { result: "blocked" }
  | { result: "error"; message?: string };

export interface SaveFlowDeps {
  ask: (item: WebItem) => Promise<PlacementAnswer>;
  save: (item: WebItem, placement?: { kind: "series" | "oneshot" }) => Promise<SaveResult>;
  toast: (t: { kind: "info" | "error"; message: string; actionLabel?: string; href?: string }) => void;
}

// One save path for the grid, the book page and the reader: D-22 placement, save call, toasts.
export async function saveWebItem(deps: SaveFlowDeps, item: WebItem): Promise<void> {
  const answer = await deps.ask(item);
  if (answer === null) return;
  const r = await deps.save(item, answer.placement);
  switch (r.result) {
    case "queued":
      deps.toast({ kind: "info", message: "Added to queue", actionLabel: "View", href: "/queue" });
      break;
    case "in_library":
      break;
    case "blocked":
      deps.toast({ kind: "error", message: "Blocked by a rule" });
      break;
    case "error":
      deps.toast({ kind: "error", message: "Could not save. Try again." });
      break;
  }
}

export type SaveStateEntry = { state: "queued" | "in_library" | "blocked"; ref?: { kind: string; id: string } } | undefined;

// The store entry (made by a save in this session) wins over the saved flag the server sent.
export function saveStateFor(item: WebItem, entry: SaveStateEntry): "idle" | "queued" | "in_library" | "blocked" {
  return entry?.state ?? (item.saved ? "in_library" : "idle");
}

export function savedHrefFor(item: WebItem, entry: SaveStateEntry): string | undefined {
  const ref = entry?.state === "in_library" && entry.ref ? entry.ref : item.saved;
  return ref ? `/item/${toPlural(ref.kind) ?? ref.kind}/${ref.id}` : undefined;
}
