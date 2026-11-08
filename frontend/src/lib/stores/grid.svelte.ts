
export type PageResult<T> = { items: T[]; total: number | null; next_page: number | null };
export type Loader<T> = (page: number, signal: AbortSignal) => Promise<PageResult<T>>;
export type GridSnapshot<T> = {
  key: string;
  items: T[];
  nextPage: number | null;
  total: number | null;
  scrollY: number;
};

type Status = "idle" | "loading" | "loading-more" | "done" | "error";

export function createGrid<T>(keyOf: (t: T) => string) {
  const state = $state({
    items: [] as T[],
    total: null as number | null,
    nextPage: null as number | null,
    status: "idle" as Status,
    error: null as Error | null,
    listKey: "" as string,
    scrollY: 0 as number,
  });

  let requestToken = 0;
  let controller: AbortController | null = null;
  let currentLoader: Loader<T> | null = null;

  function abortInFlight() {
    if (controller) {
      controller.abort();
      controller = null;
    }
  }

  function resetState() {
    requestToken++;
    abortInFlight();
    currentLoader = null;
    state.items = [];
    state.total = null;
    state.nextPage = null;
    state.status = "idle";
    state.error = null;
    state.listKey = "";
    state.scrollY = 0;
  }

  async function fetchPage(page: number, mode: "loading" | "loading-more") {
    const loader = currentLoader;
    if (!loader) return;

    const token = requestToken;
    const abortController = new AbortController();
    controller = abortController;
    state.status = mode;
    state.error = null;

    try {
      const result = await loader(page, abortController.signal);
      if (token !== requestToken) return;
      if (mode === "loading") {
        state.items = result.items;
      } else {
        // eslint-disable-next-line svelte/prefer-svelte-reactivity
        const existing = new Set(state.items.map(keyOf));
        const fresh = result.items.filter((item) => !existing.has(keyOf(item)));
        state.items = [...state.items, ...fresh];
      }
      state.total = result.total;
      state.nextPage = result.next_page;
      state.status = "done";
    } catch (err) {
      if (token !== requestToken) return;
      if (err instanceof DOMException && err.name === "AbortError") return;
      state.status = mode === "loading" ? "error" : "done";
      state.error = err instanceof Error ? err : new Error(String(err));
    } finally {
      if (controller === abortController) {
        controller = null;
      }
    }
  }

  async function open(listKey: string, loader: Loader<T>) {
    if (state.listKey === listKey && state.status === "done") return;
    requestToken++;
    abortInFlight();
    currentLoader = loader;
    state.listKey = listKey;
    state.items = [];
    state.total = null;
    state.nextPage = null;
    state.scrollY = 0;
    state.error = null;
    await fetchPage(1, "loading");
  }

  async function loadMore() {
    if (state.status !== "done" || state.nextPage === null) return;
    await fetchPage(state.nextPage, "loading-more");
  }

  async function retry() {
    if (state.items.length === 0) {
      if (!currentLoader) return;
      await fetchPage(1, "loading");
    } else {
      await loadMore();
    }
  }

  function setScrollY(y: number) {
    state.scrollY = y;
  }

  function indexOf(id: string) {
    return state.items.findIndex((item) => keyOf(item) === id);
  }

  function neighbors(id: string) {
    const idx = indexOf(id);
    if (idx === -1) return { prev: null, next: null };
    return {
      prev: idx > 0 ? state.items[idx - 1] : null,
      next: idx < state.items.length - 1 ? state.items[idx + 1] : null,
    };
  }

  function removeAt(index: number): T | undefined {
    if (index < 0 || index >= state.items.length) return undefined;
    const removed = state.items[index];
    state.items = state.items.filter((_, i) => i !== index);
    if (typeof state.total === "number") state.total--;
    return removed;
  }

  function insertAt(item: T, index: number) {
    if (state.items.some((existing) => keyOf(existing) === keyOf(item))) return;
    const clamped = Math.max(0, Math.min(index, state.items.length));
    state.items = [...state.items.slice(0, clamped), item, ...state.items.slice(clamped)];
    if (typeof state.total === "number") state.total++;
  }

  function reset() {
    resetState();
  }

  return {
    get items() { return state.items; },
    get total() { return state.total; },
    get nextPage() { return state.nextPage; },
    get status() { return state.status; },
    get error() { return state.error; },
    get listKey() { return state.listKey; },
    get scrollY() { return state.scrollY; },
    get ids() { return state.items.map(keyOf); },
    get hasMore() { return state.nextPage !== null; },
    open,
    loadMore,
    retry,
    setScrollY,
    indexOf,
    neighbors,
    removeAt,
    insertAt,
    reset,
  };
}
