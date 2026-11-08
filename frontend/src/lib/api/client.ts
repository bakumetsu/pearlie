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
export type RestoreResult = S["RestoreResult"];
export type RulesBody = S["RulesBody"];
export type RulesPut = S["RulesPut"];
export type Tag = S["Tag"];
export type Job = S["Job"];
export type JobList = S["JobList"];
export type RulesTestResult = S["RulesTestResult"];
export type ProgressResult = S["ProgressResult"];

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

export type ListParams = {
  page?: number;
  page_size?: number;
  q?: string;
  sort?: "newest" | "rating" | "random";
  favorite?: boolean;
};

export interface Api {
  search(
    p: { q: string; sources?: string[]; page?: number },
    signal?: AbortSignal,
  ): Promise<SearchResponse>;
  list(kind: Kind, p: ListParams, signal?: AbortSignal): Promise<LibraryPage>;
  save(body: SaveBody, signal?: AbortSignal): Promise<SaveAccepted>;
  health(signal?: AbortSignal): Promise<Health>;
  getItem(kind: Kind, id: string, signal?: AbortSignal): Promise<LibraryItemDetail>;
  patchItem(kind: Kind, id: string, body: PatchBody, signal?: AbortSignal): Promise<LibraryItemDetail>;
  deleteItem(kind: Kind, id: string, signal?: AbortSignal): Promise<TrashResult>;
  restore(token: string, signal?: AbortSignal): Promise<RestoreResult>;
  getRules(signal?: AbortSignal): Promise<RulesBody>;
  putRules(body: RulesPut, signal?: AbortSignal): Promise<RulesBody>;
  jobs(p: { state?: string[] }, signal?: AbortSignal): Promise<JobList>;
  retryJob(id: string, signal?: AbortSignal): Promise<Job>;
  removeJob(id: string, signal?: AbortSignal): Promise<void>;
  testRules(tags: string[], signal?: AbortSignal): Promise<RulesTestResult>;
  saveProgress(bookId: string, page: number, signal?: AbortSignal): Promise<ProgressResult>;
  pageUrl(bookId: string, n: number): string;
}

const KIND_PATHS: Record<Kind, string> = {
  images: "/api/library/stash/images",
  videos: "/api/library/stash/videos",
  series: "/api/library/komga/series",
  books: "/api/library/komga/books",
};

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
    saveProgress(bookId, page, signal) {
      return request<ProgressResult>(
        baseUrl + "/api/library/komga/books/" + encodeURIComponent(bookId) + "/progress",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ page }),
        },
        signal,
      );
    },
    pageUrl(bookId, n) {
      return baseUrl + "/api/media/komga/books/" + encodeURIComponent(bookId) + "/pages/" + n;
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
