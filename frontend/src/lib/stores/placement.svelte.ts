import { getApi } from "../api/client";
import type { Api, WebItem, PlacementSuggestion } from "../api/client";
import { options } from "./options.svelte";

export type PlacementChoice = { kind: "series" | "oneshot" };
// null = the user closed the sheet: no save.
export type PlacementAnswer = { placement?: PlacementChoice } | null;

// Sources that save into Komga; only these get the sheet.
const KOMGA_SOURCES = ["nhentai"];

export function createPlacement(deps: { api: () => Api; mode: () => string | undefined }) {
  let item: WebItem | null = $state(null);
  let suggestion: PlacementSuggestion | null = $state(null);
  let loading = $state(false);
  let error = $state("");
  let kind: "series" | "oneshot" = $state("oneshot");
  let resolver: ((a: PlacementAnswer) => void) | null = null;
  let token = 0;

  function needsSheet(it: WebItem): boolean {
    return KOMGA_SOURCES.includes(it.source) && deps.mode() === "suggest";
  }

  function finish(a: PlacementAnswer) {
    const r = resolver;
    resolver = null;
    item = null;
    token++;
    r?.(a);
  }

  // Resolves at once (no sheet) in mode auto or for a non-Komga item.
  function ask(it: WebItem): Promise<PlacementAnswer> {
    if (!needsSheet(it)) return Promise.resolve({});
    finish(null);
    const my = ++token;
    item = it;
    suggestion = null;
    error = "";
    loading = true;
    deps.api().getPlacement(it.source, it.post_id).then(
      (s) => {
        if (my !== token) return;
        suggestion = s;
        kind = s.kind;
        loading = false;
      },
      (e: unknown) => {
        if (my !== token) return;
        error = e instanceof Error ? e.message : String(e);
        loading = false;
      },
    );
    return new Promise((resolve) => {
      resolver = resolve;
    });
  }

  function toggle() {
    kind = kind === "series" ? "oneshot" : "series";
  }

  function confirm() {
    if (loading) return;
    // Send an override only when the user changed the suggestion.
    const changed = suggestion !== null && kind !== suggestion.kind;
    finish(changed ? { placement: { kind } } : {});
  }

  return {
    get item() { return item; },
    get suggestion() { return suggestion; },
    get loading() { return loading; },
    get error() { return error; },
    get kind() { return kind; },
    needsSheet,
    ask,
    toggle,
    confirm,
    cancel: () => finish(null),
  };
}

export const placement = createPlacement({
  api: () => getApi(),
  mode: () => options.values?.place_mode,
});
