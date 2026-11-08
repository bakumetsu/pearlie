import { describe, it, expect, vi } from "vitest";
import { createApi, ApiError } from "./client";

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createApi", () => {
  it("search builds /api/search?q=...&sources=a,b&page=2 and passes signal", async () => {
    const fakeFetch = vi.fn().mockResolvedValue(ok({ results: [] }));
    const api = createApi("", fakeFetch);
    const signal = new AbortController().signal;

    await api.search({ q: "hello", sources: ["a", "b"], page: 2 }, signal);

    expect(fakeFetch).toHaveBeenCalledWith(
      "/api/search?q=hello&sources=a%2Cb&page=2",
      expect.objectContaining({ signal }),
    );
  });

  it("list maps each Kind to its path and sends only defined params", async () => {
    const fakeFetch = vi.fn().mockImplementation(() => Promise.resolve(ok({ items: [] })));
    const api = createApi("", fakeFetch);
    const paths: Record<string, string> = {
      images: "/api/library/stash/images",
      videos: "/api/library/stash/videos",
      series: "/api/library/komga/series",
      books: "/api/library/komga/books",
    };

    for (const [kind, path] of Object.entries(paths)) {
      fakeFetch.mockClear();
      await api.list(kind as never, { favorite: true });
      expect(fakeFetch).toHaveBeenCalledWith(path + "?favorite=true", expect.anything());
    }
  });

  it("save sends POST with JSON body and returns job_id", async () => {
    const fakeFetch = vi.fn().mockResolvedValue(ok({ job_id: "j-1" }));
    const api = createApi("", fakeFetch);
    const body = { url: "https://example.com/img.jpg" };

    const result = await api.save(body as never);

    expect(fakeFetch).toHaveBeenCalledWith(
      "/api/save",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
    expect(result).toEqual({ job_id: "j-1" });
  });

  it("save 409 rejects with ApiError status 409, code already_saved, libraryRef", async () => {
    const fakeFetch = vi.fn().mockResolvedValue(
      ok({ code: "already_saved", message: "Dup", library_ref: { kind: "image", id: "7" } }, 409),
    );
    const api = createApi("", fakeFetch);

    const err = await api.save({ url: "x" } as never).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe("already_saved");
    expect(err.libraryRef).toEqual({ kind: "image", id: "7" });
  });

  it("422 maps code and message", async () => {
    const fakeFetch = vi.fn().mockResolvedValue(
      ok({ code: "rejected_by_rule", message: "Nope" }, 422),
    );
    const api = createApi("", fakeFetch);

    const err = await api.search({ q: "x" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("rejected_by_rule");
    expect(err.message).toBe("Nope");
  });

  it("non-JSON 500 maps to code \"error\"", async () => {
    const fakeFetch = vi.fn().mockResolvedValue(new Response("oops", { status: 500 }));
    const api = createApi("", fakeFetch);

    const err = await api.search({ q: "x" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(500);
    expect(err.code).toBe("error");
  });

  it("rejected fetch (TypeError) maps to ApiError status 0 code network", async () => {
    const fakeFetch = vi.fn().mockRejectedValue(new TypeError("failed"));
    const api = createApi("", fakeFetch);

    const err = await api.search({ q: "x" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.code).toBe("network");
  });

  it("AbortError is rethrown as-is", async () => {
    const abortErr = new DOMException("Aborted", "AbortError");
    const fakeFetch = vi.fn().mockRejectedValue(abortErr);
    const api = createApi("", fakeFetch);

    await expect(api.search({ q: "x" })).rejects.toBe(abortErr);
  });

  it("saveProgress passes keepalive and posts the page", async () => {
    const fakeFetch = vi.fn().mockResolvedValue(ok({ page: 3, completed: false }));
    const api = createApi("", fakeFetch);

    await api.saveProgress("b1", 3, undefined, { keepalive: true });

    expect(fakeFetch).toHaveBeenCalledWith(
      "/api/library/komga/books/b1/progress",
      expect.objectContaining({
        keepalive: true,
        method: "POST",
        body: '{"page":3}',
      }),
    );
  });
});
