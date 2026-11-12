import { isOffline, errorText, ApiError } from "../api/client";
import type { Api, UpdateStatus } from "../api/client";
import { toasts } from "./toasts.svelte";

export function createUpdate(api: Api, opts: { intervalMs?: number; timeoutMs?: number; reload?: () => void } = {}) {
  let status: UpdateStatus | null = $state(null);
  let loaded = $state(false);
  let offline = $state(false);
  let checking = $state(false);
  let busy = $state(false);
  let lastLatest: UpdateStatus["latest"] = $state(null);
  let error: string | null = $state(null);
  let phase: "idle" | "running" | "restarting" | "failed_rollback" = $state("idle");
  let step: string | null = $state(null);
  let applyError: string | null = $state(null);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let failureStart: number | null = null;

  const latestState = $derived.by(() => {
    if (status?.error === "rate_limited" || status?.retry_after != null) return "check_later";
    if (status?.error === "unreachable") return "unreachable";
    if (status?.available) return "available";
    if (status?.latest != null) return "up_to_date";
    return "none";
  });

  const latest = $derived.by(() => status?.latest ?? lastLatest);

  function stopPolling() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  async function tick() {
    try {
      await api.health();
      failureStart = null;
    } catch {
      if (failureStart === null) {
        failureStart = Date.now();
      } else if (Date.now() - failureStart > (opts.timeoutMs ?? 180_000)) {
        stopPolling();
        phase = "idle";
        toasts.push({ kind: "error", message: "Pearlie did not come back. Check the console." });
        return;
      }
      phase = "restarting";
      timer = setTimeout(tick, opts.intervalMs ?? 2000);
      return;
    }

    try {
      const s = await api.getUpdateStatus();
      status = s;
      step = s.step;
      switch (s.state) {
        case "running":
        case "idle":
          phase = "running";
          break;
        case "done":
          stopPolling();
          phase = "idle";
          toasts.push({ kind: "info", message: "Updated to " + s.installed.version });
          (opts.reload ?? (() => window.location.reload()))();
          return;
        case "rolled_back":
        case "failed":
          stopPolling();
          phase = "idle";
          applyError = s.error;
          toasts.push({
            kind: "error",
            message: s.error
              ? "Update failed and was rolled back: " + s.error
              : "Update failed and was rolled back",
          });
          return;
        case "failed_rollback":
          stopPolling();
          phase = "failed_rollback";
          applyError = s.error;
          return;
      }
    } catch {
      if (failureStart === null) {
        failureStart = Date.now();
      } else if (Date.now() - failureStart > (opts.timeoutMs ?? 180_000)) {
        stopPolling();
        phase = "idle";
        toasts.push({ kind: "error", message: "Pearlie did not come back. Check the console." });
        return;
      }
      phase = "restarting";
    }

    timer = setTimeout(tick, opts.intervalMs ?? 2000);
  }

  function startPolling() {
    if (timer !== null) return;
    failureStart = null;
    timer = setTimeout(tick, opts.intervalMs ?? 2000);
  }

  async function apply() {
    if (phase !== "idle") return;
    try {
      await api.applyUpdate();
      phase = "running";
      applyError = null;
      startPolling();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const code = e.code;
        if (code === "already_running") {
          phase = "running";
          applyError = null;
          startPolling();
        } else {
          toasts.push({ kind: "info", message: "Already up to date." });
          await load();
        }
      } else if (e instanceof ApiError && e.status === 503) {
        toasts.push({ kind: "error", message: "Updating is not available here." });
      } else {
        toasts.push({ kind: "error", message: "Could not start the update. Try again." });
      }
    }
  }

  function resume() {
    if (status?.state === "running" && phase === "idle") {
      phase = "running";
      startPolling();
    }
  }

  function dispose() {
    stopPolling();
  }

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
    get phase() { return phase; },
    get step() { return step; },
    get applyError() { return applyError; },
    load,
    apply,
    resume,
    dispose,
    checkNow,
    setChannel,
    setCheckEnabled,
  };
}

export type Update = ReturnType<typeof createUpdate>;
