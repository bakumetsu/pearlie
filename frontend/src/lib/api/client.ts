import { getContext, setContext } from "svelte";
import type { components } from "./schema.gen";

type S = components["schemas"];

export type LibraryItem = S["LibraryItem"];
export type WebItem = S["WebItem"];
export type Section = S["Section"];
export type SearchResponse = S["SearchResponse"];
export type SaveBody = S["SaveBody"];
export type SaveAccepted = S["SaveAccepted"];
export type Health = S["Health"];
export type LibraryPage = S["Page_LibraryItem_"];
export type LibraryItemDetail = S["LibraryItemDetail"];
export type PatchBody = S["PatchBody"];
export type TrashResult = S["TrashResult"];
export type TrashList = S["TrashList"];
export type TrashEmptied = S["TrashEmptied"];
export type TrashPurgePreview = S["TrashPurgePreview"];
export type RestoreResult = S["RestoreResult"];
export type RulesBody = S["RulesBody"];
export type RulesPut = S["RulesPut"];
export type Tag = S["Tag"];
export type Job = S["Job"];
export type JobList = S["JobList"];
export type RulesTestResult = S["RulesTestResult"];
export type ProgressResult = S["ProgressResult"];
export type ViewSettings = S["ViewSettings"];
export type ViewSettingItem = S["ViewSettingItem"];
export type ViewSettingBody = S["ViewSettingBody"];
export type PlayerSettings = S["PlayerSettings"];
export type Options = S["Options"];
export type OptionsUpdate = S["OptionsUpdate"];
export type ConnectionOut = S["ConnectionOut"];
export type ConnectionsOut = S["ConnectionsOut"];
export type ConnectionIn = S["ConnectionIn"];
export type ConnectionTest = S["TestOut"];

export type Kind = "images" | "videos" | "series" | "books";

export class ApiError extends Error {
  public status: number;
  public code: string;
  public libraryRef?: { kind: string; id: string };

  constructor(
    status: number,
    code: string,
    message: string,
    libraryRef?: { kind: string; id: string },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.libraryRef = libraryRef;
  }
}

// True when the error represents a network failure (no HTTP response).
export function isOffline(e: unknown): boolean {
  return !(e instanceof ApiError) || e.status === 0;
}

// Human-readable message for an API error; falls back to "Error <status>".
export function errorText(e: unknown): string {
  return e instanceof ApiError && e.status > 0
    ? e.message && e.message !== "Something went wrong" ? e.message : `Error ${e.status}`
    : "Something went wrong";
}

export type ListParams = {
  page?: number;
  page_size?: number;
  q?: string;
  sort?: "newest" | "rating" | "random";
  favorite?: boolean;
  seed?: number;
};

export interface Api {
  search(
    p: { q: string; sources?: string[]; page?: number; page_size?: number },
    signal?: AbortSignal,
  ): Promise<SearchResponse>;
  list(kind: Kind, p: ListParams, signal?: AbortSignal): Promise<LibraryPage>;
  save(body: SaveBody, signal?: AbortSignal): Promise<SaveAccepted>;
  health(signal?: AbortSignal): Promise<Health>;
  getItem(kind: Kind, id: string, signal?: AbortSignal): Promise<LibraryItemDetail>;
  patchItem(kind: Kind, id: string, body: PatchBody, signal?: AbortSignal): Promise<LibraryItemDetail>;
  deleteItem(kind: Kind, id: string, signal?: AbortSignal): Promise<TrashResult>;
  restore(token: string, signal?: AbortSignal): Promise<RestoreResult>;
  listTrash(signal?: AbortSignal): Promise<TrashList>;
  emptyTrash(signal?: AbortSignal): Promise<TrashEmptied>;
  purgePreview(days: number, signal?: AbortSignal): Promise<TrashPurgePreview>;
  getRules(signal?: AbortSignal): Promise<RulesBody>;
  putRules(body: RulesPut, signal?: AbortSignal): Promise<RulesBody>;
  jobs(p: { state?: string[] }, signal?: AbortSignal): Promise<JobList>;
  retryJob(id: string, signal?: AbortSignal): Promise<Job>;
  getViewSettings(signal?: AbortSignal): Promise<ViewSettings>;
  putViewSetting(source: string, body: ViewSettingBody, signal?: AbortSignal): Promise<ViewSettingItem>;
  getPlayerSettings(signal?: AbortSignal): Promise<PlayerSettings>;
  putPlayerSettings(body: PlayerSettings, signal?: AbortSignal): Promise<PlayerSettings>;
  getOptions(signal?: AbortSignal): Promise<Options>;
  putOptions(body: OptionsUpdate, signal?: AbortSignal): Promise<Options>;
  getConnections(signal?: AbortSignal): Promise<ConnectionsOut>;
  putConnection(name: string, body: Partial<ConnectionIn>, signal?: AbortSignal): Promise<ConnectionOut>;
  testConnection(name: string, signal?: AbortSignal): Promise<ConnectionTest>;
  removeJob(id: string, signal?: AbortSignal): Promise<void>;
  testRules(tags: string[], signal?: AbortSignal): Promise<RulesTestResult>;
  saveProgress(bookId: string, page: number, signal?: AbortSignal, opts?: { keepalive?: boolean }): Promise<ProgressResult>;
}

const KIND_PATHS: Record<Kind, string> = {
  images: "/api/library/stash/images",
  videos: "/api/library/stash/videos",
  series: "/api/library/komga/series",
  books: "/api/library/komga/books",
};

let _deviceClass: "touch" | "desktop" | null = null;

export function deviceClass(): "touch" | "desktop" {
  if (_deviceClass !== null) return _deviceClass;
  _deviceClass =
    typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches
      ? "touch"
      : "desktop";
  return _deviceClass;
}

export function createApi(baseUrl = "", f: typeof fetch = (...a) => fetch(...a)): Api {
  async function request<T>(url: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
    let res: Response;
    try {
      res = await f(url, { ...init, signal });
    } catch (e: unknown) {
      if (typeof e === "object" && e !== null && (e as { name?: unknown }).name === "AbortError") {
        throw e;
      }
      throw new ApiError(0, "network", "Cannot reach the server");
    }

    if (!res.ok) {
      let code = "error";
      let message = "Something went wrong";
      let libraryRef: { kind: string; id: string } | undefined;
      try {
        const body: unknown = await res.json();
        if (body !== null && typeof body === "object") {
          const b = body as Record<string, unknown>;
          if (typeof b.code === "string") code = b.code;
          if (typeof b.message === "string") message = b.message;
          if (b.library_ref !== null && typeof b.library_ref === "object") {
            const ref = b.library_ref as Record<string, unknown>;
            if (typeof ref.kind === "string" && typeof ref.id === "string") {
              libraryRef = { kind: ref.kind, id: ref.id };
            }
          }
        }
      } catch {
        // non-JSON or empty error body – keep defaults
      }
      throw new ApiError(res.status, code, message, libraryRef);
    }

    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  function buildUrl(path: string, params: Record<string, string | undefined>): string {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) {
        qs.set(k, v);
      }
    }
    const suffix = qs.toString();
    return baseUrl + path + (suffix ? "?" + suffix : "");
  }

  return {
    search(p, signal) {
      return request<SearchResponse>(
        buildUrl("/api/search", {
          q: p.q,
          sources: p.sources?.length ? p.sources.join(",") : undefined,
          page: p.page !== undefined ? String(p.page) : undefined,
          page_size: p.page_size !== undefined ? String(p.page_size) : undefined,
        }),
        undefined,
        signal,
      );
    },
    list(kind, p, signal) {
      return request<LibraryPage>(
        buildUrl(KIND_PATHS[kind], {
          page: p.page !== undefined ? String(p.page) : undefined,
          page_size: p.page_size !== undefined ? String(p.page_size) : undefined,
          q: p.q,
          sort: p.sort,
          favorite: p.favorite !== undefined ? String(p.favorite) : undefined,
          seed: p.seed !== undefined ? String(p.seed) : undefined,
        }),
        undefined,
        signal,
      );
    },
    save(body, signal) {
      return request<SaveAccepted>(
        baseUrl + "/api/save",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    health(signal) {
      return request<Health>(baseUrl + "/api/health", undefined, signal);
    },
    getItem(kind, id, signal) {
      return request<LibraryItemDetail>(
        baseUrl + "/api/library/" + kind + "/" + encodeURIComponent(id),
        undefined,
        signal,
      );
    },
    patchItem(kind, id, body, signal) {
      return request<LibraryItemDetail>(
        baseUrl + "/api/library/" + kind + "/" + encodeURIComponent(id),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    deleteItem(kind, id, signal) {
      return request<TrashResult>(
        baseUrl + "/api/library/" + kind + "/" + encodeURIComponent(id),
        { method: "DELETE" },
        signal,
      );
    },
    restore(token, signal) {
      return request<RestoreResult>(
        baseUrl + "/api/trash/" + encodeURIComponent(token) + "/restore",
        { method: "POST" },
        signal,
      );
    },
    listTrash(signal) {
      return request<TrashList>(baseUrl + "/api/trash", undefined, signal);
    },
    emptyTrash(signal) {
      return request<TrashEmptied>(baseUrl + "/api/trash", { method: "DELETE" }, signal);
    },
    purgePreview(days, signal) {
      return request<TrashPurgePreview>(baseUrl + "/api/trash/purge-preview?days=" + encodeURIComponent(String(days)), undefined, signal);
    },
    getRules(signal) {
      return request<RulesBody>(baseUrl + "/api/rules", undefined, signal);
    },
    putRules(body, signal) {
      return request<RulesBody>(
        baseUrl + "/api/rules",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    jobs(p, signal) {
      return request<JobList>(
        buildUrl("/api/jobs", {
          state: p.state?.length ? p.state.join(",") : undefined,
        }),
        undefined,
        signal,
      );
    },
    retryJob(id, signal) {
      return request<Job>(
        baseUrl + "/api/jobs/" + encodeURIComponent(id) + "/retry",
        { method: "POST" },
        signal,
      );
    },
    getViewSettings(signal) {
      return request<ViewSettings>(baseUrl + "/api/view-settings", undefined, signal);
    },
    putViewSetting(source, body, signal) {
      return request<ViewSettingItem>(
        baseUrl + "/api/view-settings/" + encodeURIComponent(source),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    getPlayerSettings(signal) {
      return request<PlayerSettings>(baseUrl + "/api/player-settings", undefined, signal);
    },
    putPlayerSettings(body, signal) {
      return request<PlayerSettings>(
        baseUrl + "/api/player-settings",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    getOptions(signal) {
      return request<Options>(
        baseUrl + "/api/options",
        {
          headers: { "X-Pearlie-Device": deviceClass() },
        },
        signal,
      );
    },
    putOptions(body, signal) {
      return request<Options>(
        baseUrl + "/api/options",
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-Pearlie-Device": deviceClass(),
          },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    getConnections(signal) {
      return request<ConnectionsOut>(
        baseUrl + "/api/connections",
        undefined,
        signal,
      );
    },
    putConnection(name, body, signal) {
      return request<ConnectionOut>(
        baseUrl + "/api/connections/" + encodeURIComponent(name),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    testConnection(name, signal) {
      return request<ConnectionTest>(
        baseUrl + "/api/connections/" + encodeURIComponent(name) + "/test",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        },
        signal,
      );
    },
    removeJob(id, signal) {
      return request<void>(
        baseUrl + "/api/jobs/" + encodeURIComponent(id),
        { method: "DELETE" },
        signal,
      );
    },
    testRules(tags, signal) {
      return request<RulesTestResult>(
        baseUrl + "/api/rules/test",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tags }),
        },
        signal,
      );
    },
    saveProgress(bookId, page, signal, opts) {
      return request<ProgressResult>(
        baseUrl + "/api/library/komga/books/" + encodeURIComponent(bookId) + "/progress",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ page }),
          keepalive: opts?.keepalive,
        },
        signal,
      );
    },
  };
}

export const API_CONTEXT_KEY = Symbol("api");

export function setApi(api: Api): void {
  setContext(API_CONTEXT_KEY, api);
}

export function getApi(): Api {
  const api = getContext<Api>(API_CONTEXT_KEY);
  if (!api) {
    throw new Error("Api context missing");
  }
  return api;
}
