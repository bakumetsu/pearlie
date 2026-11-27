import type { Api, MergedRow, MergedSite, WebItem } from "../api/client";

// The merged Discover row (D-38 sections 3.5, 4.3, 4.5). A site that is slow shows up late:
// the row polls the same URL while the answer is pending, at most POLL_MAX times.
export const POLL_MS = 3000;
export const POLL_MAX = 5;
// Same 10 min as the backend cache. A partial answer is never kept.
const ANSWER_TTL_MS = 10 * 60 * 1000;
// Plain Map on purpose: nothing renders from it, so it needs no reactivity.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const answers = new Map<string, { at: number; res: MergedRow }>();

export function clearMergedAnswers(): void {
  answers.clear();
}

type Status = "idle" | "loading" | "done" | "error";

const shown = (s: MergedSite) => s.state === "ok" || s.state === "empty";

export function createMergedRow(api: Api, opts?: { now?: () => number }) {
  const now = opts?.now ?? Date.now;
  let status: Status = $state("idle");
  let items: WebItem[] = $state([]);
  let sites: MergedSite[] = $state([]);
  let hidden = $state(0);
  let pending = $state(false);
  let error: string | null = $state(null);

  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let token = 0;
  let lastKey = "merged:";

  function stop() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    if (controller !== null) {
      controller.abort();
      controller = null;
    }
  }

  function apply(res: MergedRow) {
    items = res.items ?? [];
    sites = res.sites ?? [];
    hidden = res.hidden ?? 0;
    pending = res.pending ?? false;
    const list = sites;
    // Every site failed: nothing shown, nothing pending.
    if (!pending && list.length > 0 && !list.some(shown)) {
      status = "error";
      error = list.find((s) => s.message)?.message ?? "The sites did not answer";
    } else {
      status = "done";
      error = null;
    }
  }

  function request(polls: number) {
    const mine = token;
    controller = new AbortController();
    // `have`: the sites already on screen, so a late site is appended and no tile moves.
    const have = polls > 0 ? sites.filter(shown).map((s) => s.id) : [];
    api
      .mergedRow({ have }, controller.signal)
      .then((res) => {
        if (mine !== token) return;
        apply(res);
        if (status === "done" && !pending) {
          answers.set(lastKey, { at: now(), res });
        } else if (pending && polls < POLL_MAX) {
          timer = setTimeout(() => {
            timer = null;
            if (mine === token) request(polls + 1);
          }, POLL_MS);
        }
      })
      .catch((e: unknown) => {
        if (mine !== token) return;
        if ((e as { name?: string }).name === "AbortError") return;
        // A failed poll keeps what is shown; the first call shows the error box.
        if (polls > 0) {
          pending = false;
          return;
        }
        status = "error";
        error = e instanceof Error ? e.message : String(e);
      });
  }

  /** Load the row. `key` names the answer in the 10 min memory (rail ids and safe mode). */
  function load(o?: { key?: string; force?: boolean }) {
    stop();
    token++;
    lastKey = o?.key ?? "merged:";
    if (!o?.force) {
      const hit = answers.get(lastKey);
      if (hit && now() - hit.at <= ANSWER_TTL_MS) {
        apply(hit.res);
        return;
      }
    }
    answers.delete(lastKey);
    status = "loading";
    error = null;
    items = [];
    sites = [];
    hidden = 0;
    pending = false;
    request(0);
  }

  /** Stop the wait (pill tap): the backend call goes on and fills its cache. */
  function abort() {
    stop();
    token++;
    if (status === "loading") status = "idle";
    pending = false;
  }

  function retry() {
    load({ key: lastKey, force: true });
  }

  return {
    get status() { return status; },
    get items() { return items; },
    get sites() { return sites; },
    get hidden() { return hidden; },
    get pending() { return pending; },
    get error() { return error; },
    load,
    abort,
    retry,
  };
}
