// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { clearSearchAnswers } from "../lib/stores/search.svelte";

function web(id: string) {
  return { source: "danbooru", post_id: id, title: `post ${id}`, thumb_url: `/t/${id}`, preview_url: `/p/${id}`, width: 100, height: 100, tags: [] };
}

let n = 0;

describe("SeeAll search bar", () => {
  let searches: URLSearchParams[];
  let lists: URLSearchParams[];
  let empty: boolean;

  beforeEach(() => {
    clearSearchAnswers();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    const obs = class { observe() {} disconnect() {} unobserve() {} };
    vi.stubGlobal("IntersectionObserver", obs);
    vi.stubGlobal("ResizeObserver", obs);
    window.scrollTo = vi.fn();
    Object.defineProperty(window, "innerWidth", { value: 1024, configurable: true, writable: true });
    n += 1;
    searches = [];
    lists = [];
    empty = false;
    const json = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      if (url.pathname === "/api/view-settings") return json({}, 404);
      if (url.pathname === "/api/search/filters") return json({ sources: { danbooru: { order: ["newest", "score"], rating: ["g"], order_blocked_when: null, search: true } } });
      if (url.pathname === "/api/search") {
        searches.push(url.searchParams);
        return json({ sections: [{ id: "danbooru", items: empty ? [] : [web("1"), web("2")], next_page: null, page_size: 60 }] });
      }
      if (url.pathname.startsWith("/api/library/")) {
        lists.push(url.searchParams);
        return json({ items: [], page: 1, page_size: 60, total: 0, pages: 1, next_page: null });
      }
      return json({});
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function ready(items = true) {
    const r = render(App);
    if (items) await vi.waitFor(() => expect(r.container.querySelectorAll(".tile.web").length).toBe(2));
    return r;
  }

  it("web: typing sends nothing; Enter sends one request", async () => {
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}`);
    await ready();
    expect(searches.length).toBe(1);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "dog" } });
    expect(searches.length).toBe(1);
    await fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => expect(searches.length).toBe(2));
    expect(searches[1].get("q")).toBe(`cat${n} dog`);
    expect(location.search).toContain(`q=cat${n}+dog`);
  });

  it("the same q sends no request", async () => {
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}`);
    await ready();
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await new Promise((r) => setTimeout(r, 30));
    expect(searches.length).toBe(1);
  });

  it("library: Enter searches the library with q; keystrokes send none", async () => {
    history.replaceState({}, "", `/library/stash/images?sort=newest&x=${n}`);
    await ready(false);
    await vi.waitFor(() => expect(lists.length).toBe(1));
    const input = screen.getByRole("searchbox", { name: "Search the library" }) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "sunset" } });
    expect(lists.length).toBe(1);
    await fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => expect(lists.length).toBe(2));
    expect(lists[1].get("q")).toBe("sunset");
  });

  it("whitespace only is empty and sends no request", async () => {
    history.replaceState({}, "", `/library/stash/images?x=${n}`);
    await ready(false);
    await vi.waitFor(() => expect(lists.length).toBe(1));
    const input = screen.getByRole("searchbox") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "   " } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await new Promise((r) => setTimeout(r, 30));
    expect(lists.length).toBe(1);
  });

  it("without q it opens unfiltered in one request, even after a Discover search", async () => {
    history.replaceState({}, "", "/see-all?source=danbooru");
    await ready();
    await vi.waitFor(() => expect(searches.length).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 30));
    expect(searches.length).toBe(1);
    expect(searches[0].get("q") ?? "").toBe("");
    expect(location.search).not.toContain("q=");
  });

  it("with q in the address (from Discover), the address is used", async () => {
    history.replaceState({}, "", `/see-all?source=danbooru&q=mine${n}`);
    await ready();
    expect(searches.length).toBe(1);
    expect(searches[0].get("q")).toBe(`mine${n}`);
  });

  it("empty result shows both Clear buttons; each is one request", async () => {
    empty = true;
    history.replaceState({}, "", `/see-all?source=danbooru&q=zzz${n}&order=score`);
    await ready(false);
    await vi.waitFor(() => expect(screen.getByTestId("empty")).toBeTruthy());
    expect(screen.getByTestId("empty").textContent).toContain(`No results for “zzz${n}”`);
    expect(screen.queryByTestId("shown")).toBeNull();
    const before = searches.length;
    await fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await vi.waitFor(() => expect(searches.length).toBe(before + 1));
    expect(searches[before].has("order")).toBe(false);
    expect(searches[before].get("q")).toBe(`zzz${n}`);
    await fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    await vi.waitFor(() => expect(searches.length).toBe(before + 2));
    expect(searches[before + 1].get("q") ?? "").toBe("");
  });

  it("the search buttons are 44 px", async () => {
    const { default: src } = await import("../lib/browse/SeeAllSearch.svelte?raw");
    expect(src).toMatch(/\.ibtn \{[^}]*width: 44px; height: 44px/);
    expect(src).toMatch(/\.text \{[^}]*min-height: 44px/);
  });
});
