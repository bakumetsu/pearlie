import { ApiError } from "../api/client";
import type { Api } from "../api/client";
import { groupJobs, activeCount, pollDelayMs } from "../jobs/group";
import type { Job } from "../jobs/group";
import { toasts } from "./toasts.svelte";
import { SvelteSet } from "svelte/reactivity";

export type Jobs = ReturnType<typeof createJobs>;

export function createJobs(api: Api, opts?: { visible?: () => boolean }) {
  const visible = opts?.visible ?? (() => typeof document === "undefined" || document.visibilityState === "visible");

  let items = $state<Job[]>([]);
  let loaded = $state(false);
  let offline = $state(false);

  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let started = false;

  async function refresh(): Promise<void> {
    controller?.abort();
    controller = new AbortController();
    const signal = controller.signal;
    try {
      const res = await api.jobs({}, signal);
      items = res.items ?? [];
      offline = false;
      loaded = true;
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      offline = true;
      loaded = true;
    }
  }

  async function loop(): Promise<void> {
    await refresh();
    timer = setTimeout(loop, pollDelayMs(items, visible()));
  }

  function onVisibilityChange(): void {
    if (!visible()) return;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    loop();
  }

  function start(): void {
    if (started) return;
    started = true;
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange);
    }
    loop();
  }

  function stop(): void {
    started = false;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    controller?.abort();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    }
  }

  async function retry(id: string): Promise<void> {
    try {
      const job = await api.retryJob(id);
      items = items.map((j) => (j.id === id ? job : j));
    } catch (e) {
      if (e instanceof ApiError) {
        toasts.push({ kind: "error", message: `Could not retry: ${e.message}` });
      }
    }
  }

  async function remove(id: string): Promise<void> {
    try {
      await api.removeJob(id);
      items = items.filter((j) => j.id !== id);
    } catch (e) {
      if (e instanceof ApiError) {
        toasts.push({ kind: "error", message: `Could not remove: ${e.message}` });
      }
    }
  }

  async function clearFinished(): Promise<void> {
    const finished = items.filter((j) => j.state === "done" || j.state === "skipped");
    const removedIds = new SvelteSet<string>();
    let failed = 0;
    for (const job of finished) {
      try {
        await api.removeJob(job.id);
        removedIds.add(job.id);
      } catch {
        failed++;
      }
    }
    items = items.filter((j) => !removedIds.has(j.id));
    if (failed > 0) {
      toasts.push({ kind: "error", message: `${failed} finished job(s) failed to remove` });
    } else {
      toasts.push({ kind: "info", message: `Cleared ${removedIds.size} finished` });
    }
  }

  return {
    get items(): Job[] {
      return items;
    },
    get loaded(): boolean {
      return loaded;
    },
    get offline(): boolean {
      return offline;
    },
    get groups() {
      return groupJobs(items);
    },
    get badge(): number {
      return activeCount(items);
    },
    refresh,
    start,
    stop,
    retry,
    remove,
    clearFinished,
  };
}

