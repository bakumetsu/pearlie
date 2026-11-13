import type { Api, ViewSettingItem } from "../api/client";
import { toasts } from "./toasts.svelte";

export type ViewSettings = ViewSettingItem;

export const VIEW_SOURCES = [
  "stash_images",
  "stash_videos",
  "komga_series",
  "komga_books",
  "danbooru",
  "gelbooru",
  "rule34",
  "nhentai",
] as const;

// Neutral value used until /api/view-settings has loaded or if it fails; real values and allowed modes come from the backend.
export const PLACEHOLDER: ViewSettingItem = { mode: "grid", per_page: 60, zoom: 3, per_page_options: [60], per_page_max: 200, modes: ["grid","wall","masonry","list"] };

export function createViewSettings() {
  let sources: Record<string, ViewSettingItem> = $state({});
  let ready = $state(false);
  let _api: Api | null = null;
  let loading: Promise<void> | null = null;
  // PUTs go out one at a time per source, and only the newest response is applied.
  const chains: Record<string, Promise<void>> = {};
  const seqs: Record<string, number> = {};

  function load(api: Api): Promise<void> {
    if (loading) return loading;
    if (ready) return Promise.resolve();
    _api = api;
    loading = (async () => {
      try {
        const res = await api.getViewSettings();
        const merged: Record<string, ViewSettingItem> = {};
        for (const key of Object.keys(res.sources)) {
          let item = res.sources[key];
          if (!item.modes.includes(item.mode)) {
            item = { ...item, mode: item.modes[0] };
          }
          merged[key] = item;
        }
        sources = merged;
      } catch {
        // keep sources as-is on failure
      } finally {
        ready = true;
        loading = null;
      }
    })();
    return loading;
  }

  function get(source: string): ViewSettingItem {
    return sources[source] ?? PLACEHOLDER;
  }

  function preview(source: string, partial: { zoom?: number }): void {
    const current = sources[source] ?? PLACEHOLDER;
    sources[source] = { ...current, ...partial };
  }

  async function set(
    source: string,
    partial: Partial<Pick<ViewSettingItem, "mode" | "per_page" | "zoom">>,
  ): Promise<boolean> {
    const current = sources[source] ?? PLACEHOLDER;

    if (partial.mode !== undefined && !current.modes.includes(partial.mode)) {
      return false;
    }

    if (partial.per_page !== undefined) {
      const max = current.per_page_max;
      if (!Number.isInteger(partial.per_page) || partial.per_page < 1 || partial.per_page > max) {
        return false;
      }
    }

    const next: ViewSettingItem = { ...current, ...partial };
    sources[source] = next;

    const api = _api;
    if (api) {
      const seq = (seqs[source] = (seqs[source] ?? 0) + 1);
      const run = async () => {
        try {
          const res = await api.putViewSetting(source, {
            mode: next.mode,
            per_page: next.per_page,
            zoom: next.zoom,
          });
          if (seqs[source] === seq) {
            sources[source] = { ...sources[source], mode: res.mode, per_page: res.per_page, zoom: res.zoom };
          }
        } catch {
          toasts.push({ kind: "error", message: "Could not save view" });
        }
      };
      const done = (chains[source] ?? Promise.resolve()).then(run);
      chains[source] = done;
      await done;
    }

    return true;
  }

  return {
    get sources() { return sources; },
    get ready() { return ready; },
    load,
    get,
    preview,
    set,
  };
}

export const viewSettings = createViewSettings();

export type ViewSettingsStore = ReturnType<typeof createViewSettings>;
