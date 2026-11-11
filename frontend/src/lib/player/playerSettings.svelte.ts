import type { Api } from "../api/client";
import { toasts } from "../stores/toasts.svelte";

export function createPlayerSettings(toastsLike = toasts) {
  let autoplay = $state(false);
  let _api: Api | null = null;
  let loaded = false;

  function load(api: Api): void {
    if (loaded) return;
    loaded = true;
    _api = api;
    api.getPlayerSettings().then((res) => {
      autoplay = res.autoplay;
    }).catch(() => {
      // keep default on failure
    });
  }

  async function setAutoplay(on: boolean): Promise<void> {
    const previous = autoplay;
    autoplay = on;
    if (_api) {
      try {
        const res = await _api.putPlayerSettings({ autoplay: on });
        autoplay = res.autoplay;
      } catch {
        autoplay = previous;
        toastsLike.push({ kind: "error", message: "Could not save Autoplay" });
      }
    }
  }

  return {
    get autoplay(): boolean { return autoplay; },
    load,
    setAutoplay,
  };
}

export const playerSettings = createPlayerSettings();

export type PlayerSettingsStore = ReturnType<typeof createPlayerSettings>;
