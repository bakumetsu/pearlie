import { ApiError } from "../api/client";
import type { Api, RulesBody, RulesTestResult } from "../api/client";
import {
  draftFrom,
  addTag,
  removeTag,
  addMapping,
  removeMapping,
  setMappingTarget,
  isDirty,
  diffDraft,
  diffSummary,
  toPut,
  exportJson,
  parseImport,
  normalizeTag,
} from "../rules/draft";
import type { Draft, ListKey } from "../rules/draft";

type MappingTarget = Draft["mapping"][number]["to"];

// ── Shared leave guard ───────────────────────────────────────────
type LeaveGuard = (to: string) => boolean; // true = intercepted (prompt shown)
let leaveGuard: LeaveGuard | null = null;

export function setLeaveGuard(g: LeaveGuard | null) {
  leaveGuard = g;
}

export function guardedNavigate(
  router: { navigate(href: string): void },
  to: string
) {
  if (leaveGuard && leaveGuard(to)) return;
  router.navigate(to);
}

// ── Rules store ──────────────────────────────────────────────────
export function createRules(api: Api, opts?: { debounceMs?: number }) {
  const debounceMs = opts?.debounceMs ?? 300;

  let body: RulesBody | null = $state(null);
  let draft: Draft | null = $state(null);
  let status: "loading" | "ready" | "error" = $state("loading");
  let error: string | null = $state(null);
  let saving: boolean = $state(false);
  let conflict: boolean = $state(false);
  let tester: { tags: string[]; result: RulesTestResult | null; loading: boolean } = $state({
    tags: [],
    result: null,
    loading: false,
  });

  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  let token = 0;

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  async function load() {
    status = "loading";
    error = null;
    try {
      const res = await api.getRules();
      body = res;
      draft = draftFrom(res);
      status = "ready";
      conflict = false;
    } catch (e: unknown) {
      status = "error";
      error = e instanceof Error ? e.message : String(e);
    }
  }

  function addTo(key: ListKey, raw: string) {
    if (draft === null) return;
    draft = { ...draft, [key]: addTag(draft[key], raw) };
  }

  function removeFrom(key: ListKey, tag: string) {
    if (draft === null) return;
    draft = { ...draft, [key]: removeTag(draft[key], tag) };
  }

  function addMap(pattern: string, to: MappingTarget) {
    if (draft === null) return;
    draft = { ...draft, mapping: addMapping(draft.mapping, pattern, to) };
  }

  function removeMap(i: number) {
    if (draft === null) return;
    draft = { ...draft, mapping: removeMapping(draft.mapping, i) };
  }

  function setMapTarget(i: number, to: MappingTarget) {
    if (draft === null) return;
    draft = { ...draft, mapping: setMappingTarget(draft.mapping, i, to) };
  }

  function discard() {
    if (body !== null) {
      draft = draftFrom(body);
    }
    conflict = false;
  }

  async function save(): Promise<boolean> {
    if (body === null || draft === null) return false;
    if (!isDirty(draftFrom(body), draft)) return false;

    saving = true;
    try {
      const result = await api.putRules(toPut(body.version, draft));
      body = result;
      draft = draftFrom(result);
      conflict = false;
      error = null;
      return true;
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        if (e.code === "stale_version" || e.status === 409) {
          conflict = true;
        } else {
          error = e.message;
        }
      } else {
        error = e instanceof Error ? e.message : String(e);
      }
      return false;
    } finally {
      saving = false;
    }
  }

  function reload() {
    return load();
  }

  function importText(text: string): { ok: true } | { ok: false; error: string } {
    const result = parseImport(text);
    if (!result.ok) {
      return { ok: false, error: result.error };
    }
    draft = result.draft;
    return { ok: true };
  }

  function exportText(): string | null {
    if (body === null) return null;
    return exportJson(body);
  }

  function setTesterTags(tags: string[]) {
    clearTimer();
    if (controller !== null) {
      controller.abort();
      controller = null;
    }

    const normalized = tags.map(normalizeTag).filter((t) => t !== "");
    tester = { ...tester, tags: normalized };

    if (normalized.length === 0) {
      tester = { ...tester, result: null, loading: false };
      return;
    }

    tester = { ...tester, loading: true };

    const doTest = () => {
      token++;
      const myToken = token;
      controller = new AbortController();

      api
        .testRules(normalized, controller.signal)
        .then((res) => {
          if (myToken !== token) return;
          tester = { ...tester, result: res, loading: false };
        })
        .catch((e: unknown) => {
          if (myToken !== token) return;
          if ((e as { name?: string }).name === "AbortError") return;
          tester = { ...tester, result: null, loading: false };
        });
    };

    timer = setTimeout(doTest, debounceMs);
  }

  function destroy() {
    clearTimer();
    if (controller !== null) {
      controller.abort();
      controller = null;
    }
  }

  return {
    get body() { return body; },
    get draft() { return draft; },
    get status() { return status; },
    get error() { return error; },
    get saving() { return saving; },
    get conflict() { return conflict; },
    get tester() { return tester; },
    get dirty() { return draft !== null && body !== null && isDirty(draftFrom(body), draft); },
    get summary() {
      if (draft === null || body === null) return "No changes";
      return diffSummary(diffDraft(draftFrom(body), draft));
    },
    load,
    addTo,
    removeFrom,
    addMap,
    removeMap,
    setMapTarget,
    discard,
    save,
    reload,
    importText,
    exportText,
    setTesterTags,
    destroy,
  };
}

