// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, cleanup, waitFor, fireEvent } from "@testing-library/svelte";
import WebBook from "./WebBook.svelte";
import { API_CONTEXT_KEY } from "../lib/api/client";
import type { Api } from "../lib/api/client";
import { matchRoute } from "../lib/router";

const h = vi.hoisted(() => ({ router: null as unknown }));
vi.mock("../lib/ctx", () => ({ getRouter: () => h.router }));

beforeEach(() => {
  const m = new Map<string, string>([["pearlie.webread.v1", JSON.stringify({ "nhentai:123": { page: 3, ts: 1 } })]]);
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setup(pages = 8) {
  const api = {
    webBook: vi.fn(async () => ({
      title_main: "Web Book",
      title_sub: "Japanese",
      circle: "Circ",
      artist: "Art",
      language: "English",
      tags: { tag: ["a", "b"] },
      page_count: pages,
      page_url: "/api/media/web/nhentai/123/pages/{n}",
      page_thumb_url: "/api/media/web/nhentai/123/pages/{n}/thumb",
      item: { source: "nhentai", post_id: "123", thumb_url: "/cover", saveable: true },
    })),
    getRules: vi.fn(async () => ({ version: 1, reject: [], warn: [], require: [], mapping: {} })),
    putRules: vi.fn(async () => ({})),
  } as unknown as Api;
  const router = {
    current: () => matchRoute("/web/nhentai/123", ""),
    navigate: vi.fn(),
    canGoBack: () => false,
    subscribe: () => () => {},
    destroy: () => {},
  };
  h.router = router;
  const ctx = new Map<unknown, unknown>([[API_CONTEXT_KEY, api]]);
  return { api, router, ctx, match: matchRoute("/web/nhentai/123", "") };
}

describe("WebBook", () => {
  it("shows the book, a Continue button, all thumbnails and the last-read outline", async () => {
    const { api, router, ctx, match } = setup();
    const { container, getByText, getByLabelText } = render(WebBook, { props: { match }, context: ctx });
    await waitFor(() => expect(getByText("Web Book")).toBeTruthy());
    expect(api.webBook).toHaveBeenCalledWith("nhentai", "123");
    expect(container.querySelectorAll(".grid .thumb")).toHaveLength(8);
    expect(container.querySelector(".thumb.last")?.getAttribute("aria-label")).toBe("Page 3");
    await fireEvent.click(getByText("Continue"));
    expect(router.navigate).toHaveBeenCalledWith("/read/web/nhentai/123");
    const link = getByLabelText("Open on nhentai") as HTMLAnchorElement;
    expect(link.rel).toBe("noopener noreferrer");
  });

  it("gives at most 4 thumbnails a slot at once (2 focus, 2 prefetch)", async () => {
    const { ctx, match } = setup(20);
    const { container } = render(WebBook, { props: { match }, context: ctx });
    await waitFor(() => expect(container.querySelectorAll(".grid .thumb")).toHaveLength(20));
    await new Promise((r) => setTimeout(r, 0));
    const srcs = [...container.querySelectorAll<HTMLImageElement>(".grid img")].map((i) => i.getAttribute("src"));
    expect(srcs.filter(Boolean)).toHaveLength(4);
    expect(srcs[0]).toBe("/api/media/web/nhentai/123/pages/1/thumb");
  });

  it("rejects a tag from the ban icon", async () => {
    const { api, ctx, match } = setup();
    const { getByLabelText, getByRole } = render(WebBook, { props: { match }, context: ctx });
    await waitFor(() => getByLabelText("Reject a tag"));
    await fireEvent.click(getByLabelText("Reject a tag"));
    await fireEvent.click(getByRole("group", { name: "Reject a tag" }).querySelectorAll("button")[1]);
    await waitFor(() => expect(api.putRules).toHaveBeenCalledWith(expect.objectContaining({ reject: ["b"] })));
  });

  it("loads the new book when the route id changes", async () => {
    const { api, ctx, match } = setup();
    const r = render(WebBook, { props: { match }, context: ctx });
    await waitFor(() => expect(api.webBook).toHaveBeenCalledTimes(1));
    await r.rerender({ match: matchRoute("/web/nhentai/456", "") });
    await waitFor(() => expect(api.webBook).toHaveBeenCalledWith("nhentai", "456"));
  });

  it("hides Read and the grid for a book with no pages", async () => {
    const { ctx, match } = setup(0);
    const { container, getByText, queryByText } = render(WebBook, { props: { match }, context: ctx });
    await waitFor(() => expect(getByText("This book has no pages.")).toBeTruthy());
    expect(queryByText("Read")).toBeNull();
    expect(container.querySelector(".grid")).toBeNull();
  });
});
