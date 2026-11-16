// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { toasts } from "../lib/stores/toasts.svelte";

HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
};

function web(id: string) {
  return {
    source: "danbooru",
    post_id: id,
    title: `post ${id}`,
    thumb_url: `/t/${id}`,
    preview_url: `/p/${id}`,
    width: 100,
    height: 100,
    tags: [],
  };
}

describe("SeeAll web lightbox", () => {
  let saves: unknown[];

  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    const obs = class {
      observe() {}
      disconnect() {}
      unobserve() {}
    };
    vi.stubGlobal("IntersectionObserver", obs);
    vi.stubGlobal("ResizeObserver", obs);
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/see-all?source=danbooru&q=cat");
    saves = [];
    while (toasts.current) toasts.dismiss();
    const json = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      if (url.pathname === "/api/view-settings") return json({}, 404);
      if (url.pathname === "/api/search") {
        return json({
          sections: [{ id: "danbooru", items: [web("1"), web("2"), web("3")], total: 3, next_page: 2, pages: 3, page_size: 60 }],
        });
      }
      if (url.pathname === "/api/save") {
        saves.push(JSON.parse(String(init?.body)));
        return json({ job_id: "j1", state: "queued" }, 202);
      }
      return json({});
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function openFirst() {
    const { container } = render(App);
    await vi.waitFor(() => expect(container.querySelectorAll(".tile.web").length).toBe(3));
    await fireEvent.click(container.querySelectorAll(".open")[0]);
    await vi.waitFor(() => expect(document.querySelector("dialog .title")).not.toBeNull());
    return container;
  }

  const title = () => document.querySelector("dialog .title")?.textContent;

  it("tile click opens the lightbox with that item", async () => {
    await openFirst();
    expect(title()).toBe("post 1");
  });

  it("next and previous walk the grid", async () => {
    await openFirst();
    expect(screen.queryByRole("button", { name: "Previous" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(title()).toBe("post 2");
    await fireEvent.keyDown(document.querySelector("dialog")!, { key: "ArrowRight" });
    expect(title()).toBe("post 3");
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    await fireEvent.keyDown(document.querySelector("dialog")!, { key: "ArrowLeft" });
    expect(title()).toBe("post 2");
    await fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(title()).toBe("post 1");
  });

  it("Save calls the save API for the shown item", async () => {
    await openFirst();
    await fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await fireEvent.click(document.querySelector("dialog .save-btn")!);
    await vi.waitFor(() => expect(saves).toEqual([{ source: "danbooru", post_id: "2" }]));
  });

  it("arrow keys step the lightbox and do not change the See-all page", async () => {
    await openFirst();
    await fireEvent.keyDown(document.querySelector("dialog")!, { key: "ArrowRight" });
    expect(title()).toBe("post 2");
    expect(location.search).not.toContain("page=");
  });

  it("close (Escape closes the dialog) removes the lightbox", async () => {
    await openFirst();
    document.querySelector("dialog")!.close();
    await vi.waitFor(() => expect(document.querySelector("dialog")).toBeNull());
  });

  it("booru tiles are links to the page with ?web=, and a plain click opens the lightbox and sets it", async () => {
    const { container } = render(App);
    await vi.waitFor(() => expect(container.querySelectorAll(".tile.web").length).toBe(3));
    const a = container.querySelectorAll<HTMLAnchorElement>("a.open")[1];
    expect(a.getAttribute("href")).toBe("/see-all?source=danbooru&q=cat&web=danbooru%3A2");
    const len = history.length;
    await fireEvent.click(a);
    await vi.waitFor(() => expect(title()).toBe("post 2"));
    expect(location.search).toContain("web=danbooru%3A2");
    expect(history.length).toBe(len);
    document.querySelector("dialog")!.close();
    await vi.waitFor(() => expect(location.search).not.toContain("web="));
  });

  it("a new tab with ?web= for a post in the grid opens it", async () => {
    history.replaceState({}, "", "/see-all?source=danbooru&q=cat&web=danbooru%3A3");
    render(App);
    await vi.waitFor(() => expect(title()).toBe("post 3"));
  });

  it("a new tab with ?web= for a post outside the grid fetches it by id", async () => {
    history.replaceState({}, "", "/see-all?source=danbooru&q=cat&web=danbooru%3A99");
    const calls: string[] = [];
    const base = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      if (url.pathname === "/api/search" && url.searchParams.get("q") === "id:99") {
        calls.push(url.search);
        return Promise.resolve(new Response(JSON.stringify({ sections: [{ id: "danbooru", items: [web("99")], total: 1 }] }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      return base(input, init);
    });
    render(App);
    await vi.waitFor(() => expect(title()).toBe("post 99"));
    expect(calls[0]).toContain("sources=danbooru");
  });

  it("a post that cannot be fetched shows a toast and no lightbox", async () => {
    history.replaceState({}, "", "/see-all?source=danbooru&q=cat&web=danbooru%3A98");
    const base = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      if (url.pathname === "/api/search" && url.searchParams.get("q") === "id:98") {
        return Promise.resolve(new Response(JSON.stringify({ sections: [{ id: "danbooru", items: [], total: 0 }] }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      return base(input, init);
    });
    render(App);
    await vi.waitFor(() => expect(toasts.current?.message).toBe("Post not available"));
    expect(document.querySelector("dialog .title")).toBeNull();
    await vi.waitFor(() => expect(location.search).not.toContain("web="));
  });

  it("nhentai tile navigates to /web/nhentai/:id instead of opening lightbox", async () => {
    history.replaceState(null, "", "/see-all?source=nhentai&q=cat");
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const u = String(url);
      if (u.includes("/api/search")) {
        return new Response(
          JSON.stringify({ sections: [{ id: "nhentai", items: [{ ...web("1"), source: "nhentai" }] }] }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("null", { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(App);
    await vi.waitFor(() => expect(document.querySelectorAll(".tile.web")).toHaveLength(1));
    document.querySelector<HTMLElement>("a.open")!.click();
    await vi.waitFor(() => expect(location.pathname).toBe("/web/nhentai/1"));
    expect(document.querySelector("dialog .title")).toBeNull();
  });
});
