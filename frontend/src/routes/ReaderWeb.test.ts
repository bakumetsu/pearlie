// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, cleanup, waitFor, fireEvent } from "@testing-library/svelte";
import Reader from "./Reader.svelte";
import { API_CONTEXT_KEY } from "../lib/api/client";
import type { Api } from "../lib/api/client";
import { matchRoute } from "../lib/router";

const h = vi.hoisted(() => ({ router: null as unknown }));
vi.mock("../lib/ctx", () => ({ getRouter: () => h.router }));

beforeEach(() => {
  const m = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  });
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setup(path: string, search = "") {
  const api = {
    webBook: vi.fn(async () => ({
      title_main: "Web Book",
      page_count: 10,
      page_url: "/api/media/web/nhentai/123/pages/{n}",
      page_thumb_url: "/api/media/web/nhentai/123/pages/{n}/thumb",
      item: { source: "nhentai", post_id: "123" },
    })),
    getItem: vi.fn(async () => ({ title: "K", page_count: 4, page_url: "/k/{n}", page_thumb_url: "/kt/{n}" })),
    saveProgress: vi.fn(async () => ({})),
  } as unknown as Api;
  const router = {
    current: () => matchRoute(path, search),
    navigate: vi.fn(),
    canGoBack: () => false,
    subscribe: () => () => {},
    destroy: () => {},
  };
  h.router = router;
  const ctx = new Map<unknown, unknown>([[API_CONTEXT_KEY, api]]);
  return { api, router, ctx, match: matchRoute(path, search) };
}

describe("Reader on the web route", () => {
  it("loads the nhentai book, hides series UI, saves progress locally only", async () => {
    const { api, router, ctx, match } = setup("/read/web/nhentai/123", "?p=3");
    const { container } = render(Reader, { props: { match }, context: ctx });
    await waitFor(() => expect(api.webBook).toHaveBeenCalledWith("nhentai", "123"));
    await waitFor(() => expect(container.querySelector(".sr-only")?.textContent).toBe("Page 3 of 10"));
    expect(api.getItem).not.toHaveBeenCalled();
    await fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() =>
      expect(router.navigate).toHaveBeenCalledWith("/read/web/nhentai/123?p=4", { replace: true }),
    );
    await new Promise((r) => setTimeout(r, 900));
    expect(JSON.parse(localStorage.getItem("pearlie.webread.v1")!)["nhentai:123"].page).toBe(4);
    expect(api.saveProgress).not.toHaveBeenCalled();
  });
});
