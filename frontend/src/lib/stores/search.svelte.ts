import { ApiError } from "../api/client";
import type { Api, Section, WebItem } from "../api/client";
import { sectionsFor, serialiseQuery } from "../query";
import type { SearchState } from "../query";

export function createSearch(api: Api, opts?: { debounceMs?: number }) {
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
    const ids = sectionsFor(state.pill, state.sites, state.chips);

    // An identical query (chips + sources) is never re-sent.
    const key = JSON.stringify([serialiseQuery(state.chips), ids]);
    if (!o?.force && key === lastKey) return;
    lastKey = key;

    banner = null;
    clearTimer();
    if (controller !== null) {
      controller.abort();
      controller = null;
    }

    lastQuery = serialiseQuery(state.chips);
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

    token++;
    const myToken = token;
    const ctrl = new AbortController();

    api
      .search({ q: lastQuery, sources: [id] }, ctrl.signal)
      .then((res) => {
        if (myToken !== token) return;
        const sec = (res.sections ?? []).find((s: Section) => (s as { id: string }).id === id);
        if (sec && (sec as { error?: { message: string } }).error) {
          sections[id] = { status: "error", section: null, error: (sec as { error: { message: string } }).error.message };
        } else {
          sections[id] = { status: "done", section: sec ?? null, error: null };
        }
      })
      .catch((e: unknown) => {
        if (myToken !== token) return;
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

  async function save(item: WebItem) {
    const key = `${item.source}:${item.post_id}`;
    saves[key] = { state: "queued" };
    try {
      await api.save({ source: item.source, post_id: item.post_id });
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

  function saveStateOf(item: WebItem) {
    return saves[`${item.source}:${item.post_id}`];
  }

  return {
    get sections() { return sections; },
    get banner() { return banner; },
    get loading() { return loading; },
    get saves() { return saves; },
    run,
    retrySection,
    retryAll,
    cancel,
    save,
    saveStateOf,
  };
}
