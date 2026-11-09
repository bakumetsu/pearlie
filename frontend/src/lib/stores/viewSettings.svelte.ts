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

export const DEFAULTS: Record<string, ViewSettingItem> = {
  stash_images: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
  stash_videos: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
  komga_series: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
  komga_books: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
  danbooru: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
  gelbooru: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100], per_page_max: 100 },
  rule34: { mode: "grid", per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100], per_page_max: 100 },
  nhentai: { mode: "grid", per_page: 25, zoom: 3, per_page_options: [25], per_page_max: 25 },
};

function copyDefaults(): Record<string, ViewSettingItem> {
  const result: Record<string, ViewSettingItem> = {};
  for (const key of Object.keys(DEFAULTS)) {
    result[key] = { ...DEFAULTS[key], per_page_options: [...DEFAULTS[key].per_page_options] };
  }
  return result;
}

export function createViewSettings() {
  let sources: Record<string, ViewSettingItem> = $state(copyDefaults());
  let ready = $state(false);
  let _api: Api | null = null;
  let loading: Promise<void> | null = null;

  function load(api: Api): Promise<void> {
    if (loading) return loading;
    if (ready) return Promise.resolve();
    _api = api;
    loading = (async () => {
      try {
        const res = await api.getViewSettings();
        const merged: Record<string, ViewSettingItem> = { ...copyDefaults() };
        for (const key of Object.keys(res.sources)) {
          merged[key] = res.sources[key];
        }
        sources = merged;
      } catch {
        // keep defaults on failure
      } finally {
        ready = true;
        loading = null;
      }
    })();
    return loading;
  }

  function get(source: string): ViewSettingItem {
    return sources[source] ?? DEFAULTS["danbooru"];
  }

  function preview(source: string, partial: { zoom?: number }): void {
    const current = sources[source];
    if (!current) return;
    sources[source] = { ...current, ...partial };
  }

  async function set(
    source: string,
    partial: Partial<Pick<ViewSettingItem, "mode" | "per_page" | "zoom">>,
  ): Promise<boolean> {
    const current = sources[source];
    if (!current) return false;

    if (partial.per_page !== undefined) {
      const max = current.per_page_max;
      if (!Number.isInteger(partial.per_page) || partial.per_page < 1 || partial.per_page > max) {
        return false;
      }
    }

    const next: ViewSettingItem = { ...current, ...partial };
    sources[source] = next;

    if (_api) {
      try {
        const res = await _api.putViewSetting(source, {
          mode: next.mode,
          per_page: next.per_page,
          zoom: next.zoom,
        });
        sources[source] = { ...sources[source], mode: res.mode, per_page: res.per_page, zoom: res.zoom };
      } catch {
        toasts.push({ kind: "error", message: "Could not save view" });
      }
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
