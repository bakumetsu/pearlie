// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { gridFor } from "../lib/stores/shared.svelte";

const vid = (n: number) => ({ id: "v" + n, kind: "video", title: "Vid " + n, thumb_url: "/t" + n });

describe("Library video row queue", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    history.replaceState({}, "", "/library");
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const body = url.includes("/stash/videos")
        ? { items: [vid(1), vid(2)], page: 1, page_size: 28, total: 40, next_page: 2 }
        : { items: [], page: 1, page_size: 28, total: 0, next_page: null };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
  });

  afterEach(() => {
    cleanup();
    gridFor("videos").reset();
    vi.unstubAllGlobals();
  });

  it("a video tile click queues the row's items", async () => {
    render(App);
    await vi.waitFor(() => expect(document.querySelector('a[href="/item/videos/v1"]')).toBeTruthy());
    await fireEvent.click(document.querySelector('a[href="/item/videos/v1"]')!);
    const g = gridFor("videos");
    expect(g.items.map((i) => i.id)).toEqual(["v1", "v2"]);
    expect(g.hasNext).toBe(true);
  });
});
