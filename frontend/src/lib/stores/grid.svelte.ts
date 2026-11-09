export type PageResult<T> = {
  items: T[];
  total: number | null;
  next_page: number | null;
  page?: number | null;
  pages?: number | null;
  page_size?: number | null;
  stats?: { megapixels?: number | null; size_bytes?: number | null } | null;
  hidden?: number | null;
};

export type Loader<T> = (page: number, signal: AbortSignal) => Promise<PageResult<T>>;

export type GridSnapshot<T> = {
  key: string;
  items: T[];
  page: number;
  pages: number | null;
  total: number | null;
  scrollY: number;
};

type Status = "idle" | "loading" | "done" | "error";

export function createGrid<T>(keyOf: (t: T) => string) {
  const state = $state({
    items: [] as T[],
    total: null as number | null,
    page: 1 as number,
    requested: 1 as number,
    pages: null as number | null,
    perPage: null as number | null,
    stats: null as { megapixels?: number | null; size_bytes?: number | null } | null,
    hidden: 0 as number,
    hasNext: false as boolean,
    status: "idle" as Status,
    error: null as Error | null,
    listKey: "" as string,
    scrollY: 0 as number,
  });

  let requestToken = 0;
  let crossed = false;
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
    state.page = 1;
    state.requested = 1;
    state.pages = null;
    state.perPage = null;
    state.stats = null;
    state.hidden = 0;
    state.hasNext = false;
    state.status = "idle";
    state.error = null;
    state.listKey = "";
    state.scrollY = 0;
    crossed = false;
  }

  async function fetchPage(page: number) {
    const loader = currentLoader;
    if (!loader) return;

    const token = requestToken;
    const abortController = new AbortController();
    controller = abortController;
    state.requested = page;
    state.status = "loading";
    state.error = null;

    try {
      const result = await loader(page, abortController.signal);
      if (token !== requestToken) return;
      state.items = result.items;
      state.total = result.total;
      state.page = result.page ?? page;
      state.pages = result.pages ?? null;
      state.perPage = result.page_size ?? null;
      state.stats = result.stats ?? null;
      state.hidden = result.hidden ?? 0;
      state.hasNext = result.next_page != null;
      state.status = "done";
    } catch (err) {
      if (token !== requestToken) return;
      if (err instanceof DOMException && err.name === "AbortError") return;
      state.status = "error";
      state.error = err instanceof Error ? err : new Error(String(err));
    } finally {
      if (controller === abortController) {
        controller = null;
      }
    }
  }

  async function open(listKey: string, loader: Loader<T>, page = 1) {
    if (state.listKey === listKey && state.status === "done" && state.page === page) return;
    requestToken++;
    abortInFlight();
    currentLoader = loader;
    state.listKey = listKey;
    state.items = [];
    state.page = page;
    state.total = null;
    state.pages = null;
    state.perPage = null;
    state.stats = null;
    state.hidden = 0;
    state.hasNext = false;
    state.scrollY = 0;
    state.error = null;
    await fetchPage(page);
  }

  async function goTo(page: number) {
    if (!currentLoader) return;
    const p = Math.max(1, Math.floor(page));
    requestToken++;
    abortInFlight();
    state.items = [];
    await fetchPage(p);
  }

  async function retry() {
    if (!currentLoader) return;
    await fetchPage(state.requested);
  }

  function setScrollY(y: number) {
    state.scrollY = y;
  }

  function markCrossed() {
    crossed = true;
  }

  function takeCrossed(): boolean {
    const c = crossed;
    crossed = false;
    return c;
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
    if (typeof state.total === "number") {
      state.total--;
      if (state.pages !== null && typeof state.perPage === "number" && state.perPage > 0) {
        state.pages = Math.max(1, Math.ceil(state.total / state.perPage));
      }
    }
    return removed;
  }

  function insertAt(item: T, index: number) {
    if (state.items.some((existing) => keyOf(existing) === keyOf(item))) return;
    const clamped = Math.max(0, Math.min(index, state.items.length));
    state.items = [...state.items.slice(0, clamped), item, ...state.items.slice(clamped)];
    if (typeof state.total === "number") {
      state.total++;
      if (state.pages !== null && typeof state.perPage === "number" && state.perPage > 0) {
        state.pages = Math.max(1, Math.ceil(state.total / state.perPage));
      }
    }
  }

  function removeById(id: string): { item: T; index: number } | null {
    const index = indexOf(id);
    if (index === -1) return null;
    const item = removeAt(index);
    return item === undefined ? null : { item, index };
  }

  function restore(entry: { item: T; index: number }) {
    insertAt(entry.item, entry.index);
  }

  function snapshot(): GridSnapshot<T> {
    return {
      key: `${state.listKey}|p${state.page}|n${state.perPage ?? 0}`,
      items: [...state.items],
      page: state.page,
      pages: state.pages,
      total: state.total,
      scrollY: state.scrollY,
    };
  }

  function restoreSnapshot(snap: GridSnapshot<T>) {
    state.items = [...snap.items];
    state.page = snap.page;
    state.requested = snap.page;
    state.pages = snap.pages;
    state.hasNext = snap.pages != null && snap.page < snap.pages;
    state.total = snap.total;
    state.scrollY = snap.scrollY;
    state.status = "done";
  }

  function reset() {
    resetState();
  }

  return {
    get items() { return state.items; },
    get total() { return state.total; },
    get page() { return state.page; },
    get requested() { return state.requested; },
    get pages() { return state.pages; },
    get perPage() { return state.perPage; },
    get stats() { return state.stats; },
    get hidden() { return state.hidden; },
    get hasNext() { return state.hasNext; },
    get status() { return state.status; },
    get error() { return state.error; },
    get listKey() { return state.listKey; },
    get scrollY() { return state.scrollY; },
    get ids() { return state.items.map(keyOf); },
    open,
    goTo,
    retry,
    setScrollY,
    markCrossed,
    takeCrossed,
    indexOf,
    neighbors,
    removeAt,
    insertAt,
    removeById,
    restore,
    snapshot,
    restoreSnapshot,
    reset,
  };
}
