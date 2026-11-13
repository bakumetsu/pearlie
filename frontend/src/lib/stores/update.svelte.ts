import { isOffline, errorText, ApiError } from "../api/client";
import type { Api, ChangeBlock, UpdateChangelog, UpdateStatus } from "../api/client";
import { toasts } from "./toasts.svelte";

export function createUpdate(api: Api, opts: { intervalMs?: number; timeoutMs?: number; maxMs?: number; retryMs?: number; reload?: () => void } = {}) {
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
  let changelog: UpdateChangelog | null = $state(null);
  let releases: ChangeBlock[] = $state([]);
  let hasMore = $state(false);
  let loadingMore = $state(false);
  let moreError = $state(false);
  let changelogLoading = $state(false);
  let changelogFailed = $state(false);
  let changelogGen = 0;
  let viewOverride: "main" | "dev" | null = $state(null);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let failureStart: number | null = null;
  let startedAt: number | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let loadRestart = false;
  let disposed = false;

  const latestState = $derived.by(() => {
    if (status?.available) return "available";
    if (status?.error === "rate_limited" || status?.retry_after != null) return "check_later";
    if (status?.error === "unreachable") return "unreachable";
    if (status?.latest != null) return "up_to_date";
    return "none";
  });

  const latest = $derived.by(() => status?.latest ?? lastLatest);

  const viewChannel = $derived.by((): "main" | "dev" => viewOverride ?? status?.channel ?? "main");

  const PAGE = 10;

  function appendReleases(blocks: ChangeBlock[]) {
    const seen = new Set(releases.map((r) => r.title));
    const fresh = blocks.filter((b) => !seen.has(b.title));
    releases = [...releases, ...fresh];
  }

  async function loadChangelog(refresh = false) {
    const want = viewChannel;
    const gen = ++changelogGen;
    changelogLoading = true;
    changelogFailed = false;
    moreError = false;
    loadingMore = false;
    try {
      const c = await api.getUpdateChangelog({ channel: want, refresh, offset: 0, limit: PAGE });
      if (gen !== changelogGen) return;
      changelog = c;
      releases = [];
      appendReleases(c.history);
      hasMore = c.has_more;
    } catch {
      if (gen !== changelogGen) return;
      changelogFailed = true;
    } finally {
      if (gen === changelogGen) changelogLoading = false;
    }
  }

  /** Status first (the view starts on the installed channel), then page 0. */
  async function openChangelog() {
    await load(false);
    await loadChangelog(false);
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    const want = viewChannel;
    const gen = changelogGen;
    const offset = releases.filter((r) => r.version != null).length;
    loadingMore = true;
    moreError = false;
    try {
      const c = await api.getUpdateChangelog({ channel: want, offset, limit: PAGE });
      if (gen !== changelogGen) return;
      if (c.history.length === 0 && (c.unavailable || c.stale)) {
        moreError = true;
      } else {
        appendReleases(c.history);
        hasMore = c.has_more;
      }
    } catch {
      if (gen === changelogGen) moreError = true;
    } finally {
      if (gen === changelogGen) loadingMore = false;
    }
  }

  async function setView(ch: "main" | "dev") {
    if (viewChannel === ch) return;
    viewOverride = ch;
    changelog = null;
    releases = [];
    hasMore = false;
    await loadChangelog();
  }

  function stopPolling() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function giveUp(message: string) {
    stopPolling();
    phase = "idle";
    toasts.push({ kind: "error", message });
  }

  async function tick() {
    if (startedAt !== null && Date.now() - startedAt > (opts.maxMs ?? 600_000)) {
      giveUp("Update did not finish. Check /opt/pearlie/update.log.");
      return;
    }
    try {
      await api.health();
      failureStart = null;
    } catch {
      if (failureStart === null) {
        failureStart = Date.now();
      } else if (Date.now() - failureStart > (opts.timeoutMs ?? 180_000)) {
        giveUp("Pearlie did not come back. Check the console.");
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
          try {
            sessionStorage.setItem("pearlie.update.notice", "Updated to " + s.installed.version);
          } catch {
            // storage blocked: the toast below still shows
          }
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
        giveUp("Pearlie did not come back. Check the console.");
        return;
      }
      phase = "restarting";
    }

    timer = setTimeout(tick, opts.intervalMs ?? 2000);
  }

  function startPolling() {
    if (timer !== null) return;
    failureStart = null;
    startedAt = Date.now();
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

  function stopRetry() {
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  }

  function dispose() {
    disposed = true;
    stopPolling();
    stopRetry();
  }

  // A failed status load is never a dead end: probe health (a restart shows
  // "Restarting…") and keep retrying until the status arrives.
  async function loadFailed(refresh: boolean) {
    try {
      await api.health();
    } catch {
      if (phase === "idle") {
        phase = "restarting";
        loadRestart = true;
      }
    }
    if (disposed || retryTimer !== null) return;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      void load(refresh);
    }, opts.retryMs ?? 5000);
  }

  async function retry() {
    stopRetry();
    await load(true);
  }

  async function load(refresh = false) {
    try {
      const notice = sessionStorage.getItem("pearlie.update.notice");
      if (notice) {
        sessionStorage.removeItem("pearlie.update.notice");
        toasts.push({ kind: "info", message: notice });
      }
    } catch {
      // storage blocked
    }
    try {
      const result = await api.getUpdateStatus(refresh ? { refresh: true } : undefined);
      status = result;
      if (result.latest) lastLatest = result.latest;
      offline = false;
      error = null;
      stopRetry();
      if (loadRestart) {
        loadRestart = false;
        if (phase === "restarting") phase = "idle";
      }
      if (phase === "idle") resume();
    } catch (e) {
      if (isOffline(e)) {
        offline = true;
      } else {
        error = errorText(e);
      }
      await loadFailed(refresh);
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
      viewOverride = null;
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
    get changelog() { return changelog; },
    get releases() { return releases; },
    get hasMore() { return hasMore; },
    get loadingMore() { return loadingMore; },
    get moreError() { return moreError; },
    get changelogLoading() { return changelogLoading; },
    get changelogFailed() { return changelogFailed; },
    get viewChannel() { return viewChannel; },
    get phase() { return phase; },
    get step() { return step; },
    get applyError() { return applyError; },
    load,
    retry,
    apply,
    resume,
    dispose,
    checkNow,
    setChannel,
    setView,
    openChangelog,
    loadMore,
    loadChangelog,
    setCheckEnabled,
  };
}

export type Update = ReturnType<typeof createUpdate>;
