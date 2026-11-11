import type { Api, Options, OptionsUpdate } from "../api/client";
import { toasts } from "./toasts.svelte";
import { sfw } from "./sfw.svelte";
import { player } from "../player/player.svelte";

const VALID_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];

function mergePatch(a: OptionsUpdate, b: OptionsUpdate): OptionsUpdate {
  const merged = { ...a, ...b };
  if (a.source_pace || b.source_pace) {
    merged.source_pace = { ...a.source_pace, ...b.source_pace };
  }
  return merged;
}

export function createOptions(deps: {
  sfw: { set(on: boolean): void };
  player: { loadRate(r: number): void };
  storage?: Pick<Storage, "getItem" | "removeItem">;
  debounceMs?: number;
}) {
  let values: Options | null = $state(null);
  let ready = $state(false);
  let _api: Api | null = null;
  let loading: Promise<void> | null = null;
  let pendingPatch: OptionsUpdate = {};
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let lastConfirmed: Options | null = null;
  let early: OptionsUpdate = {};
  let failed = false;
  const debounceMs = deps.debounceMs ?? 300;
  const storage = deps.storage ?? (typeof localStorage !== "undefined" ? localStorage : undefined);

  function load(api: Api): Promise<void> {
    if (loading) return loading;
    if (ready && !failed) return Promise.resolve();
    _api = api;
    loading = (async () => {
      let res: Options;
      try {
        res = await api.getOptions();
      } catch {
        ready = true;
        failed = true;
        loading = null;
        if (Object.keys(early).length > 0) {
          // A change made meanwhile must not vanish without feedback
          early = {};
          toasts.push({ kind: "error", message: "Could not save options" });
        }
        return;
      }
      failed = false;

      // Migration: only for fields the server reports as unset
      const patch: OptionsUpdate = {};
      const migratedKeys: string[] = [];

      try {
        if (!res.sfw_set) {
          const stored = storage?.getItem("pearlie.sfw");
          if (stored === "1" || stored === "0") {
            patch.sfw = stored === "1";
            migratedKeys.push("pearlie.sfw");
          }
        } else {
          // Already set on server – just clean up the old key
          storage?.removeItem("pearlie.sfw");
        }

        if (!res.player_rate_set) {
          const stored = storage?.getItem("pearlie.player.rate");
          if (stored !== null) {
            const num = Number(stored);
            if (VALID_RATES.includes(num)) {
              patch.player_rate = num;
              migratedKeys.push("pearlie.player.rate");
            }
          }
        } else {
          storage?.removeItem("pearlie.player.rate");
        }
      } catch {
        // Storage access failed – ignore, proceed with what we have
      }

      if (Object.keys(patch).length > 0) {
        try {
          res = await api.putOptions(patch);
          // Only remove migrated keys after a confirmed save
          for (const key of migratedKeys) {
            try {
              storage?.removeItem(key);
            } catch { /* ignore */ }
          }
        } catch {
          // PUT failed – keep original GET result, leave keys in place
        }
      }

      values = res;
      lastConfirmed = res;
      deps.sfw.set(res.sfw);
      deps.player.loadRate(res.player_rate);
      ready = true;
      if (Object.keys(early).length > 0) {
        const queued = early;
        early = {};
        set(queued);
      }
    })();
    return loading;
  }

  function set(patch: OptionsUpdate): void {
    if (!_api || !values) {
      // Changed before the first GET came back: keep it and send it once loaded
      early = mergePatch(early, patch);
      // The first load failed: retry it; a second failure toasts and drops the queue
      if (failed && _api) void load(_api);
      return;
    }

    // Optimistic update
    const defined = Object.fromEntries(Object.entries(patch).filter(([k, v]) => v !== null && v !== undefined && k !== "source_pace"));
    values = { ...values, ...defined };
    if (patch.source_pace && values.source_pace) {
      const oldPace = values.source_pace;
      const newPace: typeof oldPace = { ...oldPace };
      for (const [site, n] of Object.entries(patch.source_pace)) {
        if (site in oldPace) {
          newPace[site] = { ...oldPace[site], value: n };
        }
      }
      values = { ...values, source_pace: newPace };
    }

    if (patch.sfw !== undefined && patch.sfw !== null) deps.sfw.set(patch.sfw);
    if (patch.player_rate !== undefined && patch.player_rate !== null) deps.player.loadRate(patch.player_rate);

    // Accumulate into pending
    pendingPatch = mergePatch(pendingPatch, patch);

    // Debounce
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      debounceTimer = null;
      const toSend = pendingPatch;
      pendingPatch = {};
      try {
        const res = await _api!.putOptions(toSend);
        values = res;
        lastConfirmed = res;
        deps.sfw.set(res.sfw);
        deps.player.loadRate(res.player_rate);
      } catch {
        if (lastConfirmed) {
          values = lastConfirmed;
          deps.sfw.set(lastConfirmed.sfw);
          deps.player.loadRate(lastConfirmed.player_rate);
        }
        toasts.push({ kind: "error", message: "Could not save options" });
      }
    }, debounceMs);
  }

  return {
    get values(): Options | null { return values; },
    get ready(): boolean { return ready; },
    load,
    set,
  };
}

export const options = createOptions({
  sfw: { set: (on: boolean) => sfw?.set(on) },
  player: { loadRate: (r: number) => player?.loadRate(r) },
});

if (sfw) sfw.onChange = (on: boolean) => options.set({ sfw: on });
if (player) player.onRateChange = (r: number) => options.set({ player_rate: r });

export type OptionsStore = ReturnType<typeof createOptions>;
