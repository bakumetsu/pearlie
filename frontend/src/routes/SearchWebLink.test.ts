// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";

HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
};

const web = (id: string) => ({ source: "danbooru", post_id: id, title: `post ${id}`, thumb_url: `/t/${id}`, preview_url: `/p/${id}`, width: 100, height: 100, tags: [] });

describe("Discover booru tile links", () => {
  let idQueries: string[];

  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    idQueries = [];
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      let body: unknown = {};
      if (url.pathname === "/api/search") {
        const q = url.searchParams.get("q") ?? "";
        if (q.startsWith("id:")) {
          idQueries.push(q);
          body = { sections: [{ id: "danbooru", items: [web(q.slice(3))], total: 1 }] };
        } else {
          body = { sections: [{ id: "danbooru", title: "Danbooru", items: [web("1"), web("2")], total: 2 }] };
        }
      }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const title = () => document.querySelector("dialog .title")?.textContent;

  it("a tile is a link with ?web=, a plain click opens the lightbox and keeps the history length", async () => {
    history.replaceState({}, "", "/?q=cat&sites=danbooru");
    const { container } = render(App);
    await vi.waitFor(() => expect(container.querySelectorAll(".tile.web").length).toBe(2));
    const a = container.querySelectorAll<HTMLAnchorElement>("a.open")[1];
    expect(a.getAttribute("href")).toContain("web=danbooru%3A2");
    const len = history.length;
    await fireEvent.click(a);
    await vi.waitFor(() => expect(title()).toBe("post 2"));
    expect(location.search).toContain("web=danbooru%3A2");
    expect(history.length).toBe(len);
  });

  it("a new tab with ?web= for a post in the rows opens it without a fetch by id", async () => {
    history.replaceState({}, "", "/?q=cat&sites=danbooru&web=danbooru%3A1");
    render(App);
    await vi.waitFor(() => expect(title()).toBe("post 1"));
    expect(idQueries).toEqual([]);
  });

  it("a new tab with ?web= for a post outside the rows fetches it by id", async () => {
    history.replaceState({}, "", "/?q=cat&sites=danbooru&web=danbooru%3A77");
    render(App);
    await vi.waitFor(() => expect(title()).toBe("post 77"));
    expect(idQueries).toEqual(["id:77"]);
  });
});
