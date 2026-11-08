import { describe, it, expect, vi } from "vitest";
import { createApi, ApiError } from "./client";

function ok(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("client item & rules", () => {
  it("getItem sends GET to the item URL with no method override", async () => {
    const fake = vi.fn().mockResolvedValue(ok({}));
    const api = createApi("", fake);
    await api.getItem("videos", "7");
    expect(fake).toHaveBeenCalledWith("/api/library/videos/7", { signal: undefined });
  });

  it("patchItem sends PATCH with JSON body and content-type", async () => {
    const fake = vi.fn().mockResolvedValue(ok({}));
    const api = createApi("", fake);
    await api.patchItem("videos", "7", { rating: 4 });
    expect(fake).toHaveBeenCalledWith("/api/library/videos/7", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: 4 }),
      signal: undefined,
    });
  });

  it("deleteItem sends DELETE to the series item URL", async () => {
    const fake = vi.fn().mockResolvedValue(ok({}));
    const api = createApi("", fake);
    await api.deleteItem("series", "s1");
    expect(fake).toHaveBeenCalledWith("/api/library/series/s1", {
      method: "DELETE",
      signal: undefined,
    });
  });

  it("restore POSTs to the encoded trash URL", async () => {
    const fake = vi.fn().mockResolvedValue(ok({}));
    const api = createApi("", fake);
    await api.restore("tok 1");
    expect(fake).toHaveBeenCalledWith("/api/trash/tok%201/restore", {
      method: "POST",
      signal: undefined,
    });
  });

  it("putRules sends PUT with the body", async () => {
    const fake = vi.fn().mockResolvedValue(ok({}));
    const api = createApi("", fake);
    const body = { version: 1, reject: ["a"] };
    await api.putRules(body);
    expect(fake).toHaveBeenCalledWith("/api/rules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: undefined,
    });
  });

  it("restore throws ApiError with status 404 and code not_found on 404", async () => {
    const fake = vi.fn().mockResolvedValue(
      ok({ code: "not_found", message: "gone" }, 404),
    );
    const api = createApi("", fake);
    const err = (await api.restore("tok 1").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.code).toBe("not_found");
  });
});
