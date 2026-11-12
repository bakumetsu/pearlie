import { isOffline, errorText } from "../api/client";
import type { Api, UpdateStatus } from "../api/client";
import { toasts } from "./toasts.svelte";

export function createUpdate(api: Api) {
  let status: UpdateStatus | null = $state(null);
  let loaded = $state(false);
  let offline = $state(false);
  let checking = $state(false);
  let busy = $state(false);
  let lastLatest: UpdateStatus["latest"] = $state(null);
  let error: string | null = $state(null);

  const latestState = $derived.by(() => {
    if (status?.error === "rate_limited" || status?.retry_after != null) return "check_later";
    if (status?.error === "unreachable") return "unreachable";
    if (status?.available) return "available";
    if (status?.latest != null) return "up_to_date";
    return "none";
  });

  const latest = $derived.by(() => status?.latest ?? lastLatest);

  async function load(refresh = false) {
    try {
      const result = await api.getUpdateStatus(refresh ? { refresh: true } : undefined);
      status = result;
      if (result.latest) lastLatest = result.latest;
      offline = false;
      error = null;
    } catch (e) {
      if (isOffline(e)) {
        offline = true;
      } else {
        error = errorText(e);
      }
    } finally {
      loaded = true;
    }
  }

  async function checkNow() {
    checking = true;
    try {
      const result = await api.getUpdateStatus({ refresh: true, manual: true });
      status = result;
      if (result.latest) lastLatest = result.latest;
      offline = false;
      error = null;
    } catch (e) {
      if (isOffline(e)) {
        offline = true;
      } else {
        error = errorText(e);
      }
    } finally {
      checking = false;
    }
  }

  async function setChannel(ch: "main" | "dev") {
    if (status?.channel === ch) return;
    busy = true;
    try {
      const result = await api.putUpdateSettings({ channel: ch });
      status = result;
      await checkNow();
    } catch {
      toasts.push({ kind: "error", message: "Could not switch channel. Try again." });
    } finally {
      busy = false;
    }
  }

  async function setCheckEnabled(on: boolean) {
    busy = true;
    try {
      const result = await api.putUpdateSettings({ check_enabled: on });
      status = result;
    } catch {
      toasts.push({ kind: "error", message: "Could not save. Try again." });
    } finally {
      busy = false;
    }
  }

  return {
    get status() { return status; },
    get loaded() { return loaded; },
    get offline() { return offline; },
    get checking() { return checking; },
    get busy() { return busy; },
    get lastLatest() { return lastLatest; },
    get error() { return error; },
    get latest() { return latest; },
    get latestState() { return latestState; },
    load,
    checkNow,
    setChannel,
    setCheckEnabled,
  };
}

export type Update = ReturnType<typeof createUpdate>;
