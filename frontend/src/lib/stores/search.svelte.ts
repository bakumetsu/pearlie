import { untrack } from "svelte";
import { ApiError } from "../api/client";
import type { Api, Section, WebItem } from "../api/client";
import { sectionsFor, serialiseQuery } from "../query";
import type { SearchState } from "../query";
import type { Job } from "../jobs/group";
import { settleQueued } from "../web/saveFlow";

// The last Discover search, kept for the page session so See all can start from it (one way: See all never writes it).
let discoverQuery = "";

export function getLastDiscoverQuery(): string {
  return discoverQuery;
}

export function createSearch(api: Api, opts?: { debounceMs?: number; remember?: boolean }) {
  const debounceMs = opts?.debounceMs ?? 300;

  let sections: Record<string, { status: "loading" | "done" | "error"; section: Section | null; error: string | null }> =
    $state({});
  let banner: string | null = $state(null);
  let loading: boolean = $state(false);
  const saves: Record<string, { state: "queued" | "in_library" | "blocked"; ref?: { kind: string; id: string } }> =
    $state({});

  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  let token = 0;
  // Retries have their own tokens: a retry must not make the main search or another retry stale.
  let retryGen = 0;
  const retryTokens: Record<string, number> = {};
  let lastQuery = "";
  let lastState: SearchState | null = null;
  let lastKey: string | null = null;

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function run(state: SearchState, o?: { immediate?: boolean; force?: boolean }) {
    const ids = sectionsFor(state.pill, state.sites);

    // An identical query (chips + sources) is never re-sent.
    // The order of the rows is not part of the query: a reorder only moves them.
    const key = JSON.stringify([serialiseQuery(state.chips), [...ids].sort()]);
    if (!o?.force && key === lastKey) {
      // Untracked: run() is called from an effect, which must not depend on the rows.
      untrack(() => {
        const moved: typeof sections = {};
        for (const id of ids) if (sections[id] !== undefined) moved[id] = sections[id];
        if (Object.keys(moved).length === Object.keys(sections).length && Object.keys(moved).join() !== Object.keys(sections).join()) sections = moved;
      });
      return;
    }
    lastKey = key;

    banner = null;
    clearTimer();
    if (controller !== null) {
      controller.abort();
      controller = null;
    }

    retryGen++;
    lastQuery = serialiseQuery(state.chips);
    if (opts?.remember) discoverQuery = lastQuery;
    lastState = state;

    if (ids.length === 0) {
      sections = {};
      loading = false;
      return;
    }

    sections = {};
    for (const id of ids) {
      sections[id] = { status: "loading", section: null, error: null };
    }
    loading = true;

    const doSearch = () => {
      token++;
      const myToken = token;
      controller = new AbortController();

      api
        .search({ q: lastQuery, sources: ids }, controller.signal)
        .then((res) => {
          if (myToken !== token) return;
          loading = false;
          for (const id of ids) {
            const sec = (res.sections ?? []).find((s: Section) => (s as { id: string }).id === id);
            if (sec && (sec as { error?: { message: string } }).error) {
              sections[id] = { status: "error", section: null, error: (sec as { error: { message: string } }).error.message };
            } else {
              sections[id] = { status: "done", section: sec ?? null, error: null };
            }
          }
        })
        .catch((e: unknown) => {
          if (myToken !== token) return;
          if ((e as { name?: string }).name === "AbortError") return;
          loading = false;
          banner = "Search failed";
          const msg = e instanceof Error ? e.message : String(e);
          for (const id of ids) {
            sections[id] = { status: "error", section: null, error: msg };
          }
        });
    };

    if (o?.immediate) {
      doSearch();
    } else {
      timer = setTimeout(doSearch, debounceMs);
    }
  }

  function retrySection(id: string) {
    if (sections[id] === undefined) return;
    sections[id] = { status: "loading", section: null, error: null };

    const gen = retryGen;
    const myToken = (retryTokens[id] = (retryTokens[id] ?? 0) + 1);
    const stale = () => gen !== retryGen || myToken !== retryTokens[id];
    const ctrl = new AbortController();

    api
      .search({ q: lastQuery, sources: [id] }, ctrl.signal)
      .then((res) => {
        if (stale()) return;
        const sec = (res.sections ?? []).find((s: Section) => (s as { id: string }).id === id);
        if (sec && (sec as { error?: { message: string } }).error) {
          sections[id] = { status: "error", section: null, error: (sec as { error: { message: string } }).error.message };
        } else {
          sections[id] = { status: "done", section: sec ?? null, error: null };
        }
      })
      .catch((e: unknown) => {
        if (stale()) return;
        if ((e as { name?: string }).name === "AbortError") return;
        const msg = e instanceof Error ? e.message : String(e);
        sections[id] = { status: "error", section: null, error: msg };
      });
  }

  function retryAll() {
    if (lastState !== null) run(lastState, { immediate: true, force: true });
  }

  function cancel() {
    lastKey = null;
    clearTimer();
    if (controller !== null) {
      controller.abort();
      controller = null;
    }
    loading = false;
  }

  async function save(item: WebItem, placement?: { kind: "series" | "oneshot" }) {
    const key = `${item.source}:${item.post_id}`;
    saves[key] = { state: "queued" };
    try {
      await api.save({ source: item.source, post_id: item.post_id, ...(placement ? { placement } : {}) });
      return { result: "queued" as const };
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 409) {
        saves[key] = { state: "in_library", ref: e.libraryRef };
        return { result: "in_library" as const, ref: e.libraryRef };
      }
      if (e instanceof ApiError && e.status === 422) {
        saves[key] = { state: "blocked" };
        return { result: "blocked" as const };
      }
      delete saves[key];
      const message = e instanceof Error ? e.message : String(e);
      return { result: "error" as const, message };
    }
  }

  function settle(jobs: Job[]) {
    const queued = Object.keys(saves).filter((k) => saves[k]?.state === "queued");
    if (queued.length === 0) return;
    for (const [key, next] of Object.entries(settleQueued(queued, jobs))) {
      if (next === "idle") delete saves[key];
      else saves[key] = next;
    }
  }

  function saveStateOf(item: WebItem) {
    return saves[`${item.source}:${item.post_id}`];
  }

  return {
    get sections() { return sections; },
    get banner() { return banner; },
    get loading() { return loading; },
    get saves() { return saves; },
    get lastQuery() { return lastQuery; },
    run,
    retrySection,
    retryAll,
    cancel,
    save,
    saveStateOf,
    settle,
  };
}
