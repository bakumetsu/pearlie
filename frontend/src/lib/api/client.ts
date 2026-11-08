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
