// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";

function tile(id: string) {
  return {
    kind: "image",
    id,
    title: `img ${id}`,
    thumb_url: `/t/${id}`,
    source: "stash",
    tags: [],
  };
}

describe("SeeAll paging", () => {
  let pages: number[];
  let sizes: number[];
  let served: (requested: number) => number;

  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    });
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    );
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    );
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/see-all?source=stash_images");
    pages = [];
    sizes = [];
    served = (r) => Math.min(r, 3);
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        "http://localhost",
      );
      if (url.pathname === "/api/view-settings") {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 404,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.pathname.startsWith("/api/library/")) {
        const requested = Number(url.searchParams.get("page") ?? "1");
        const p = served(requested);
        pages.push(requested);
        sizes.push(Number(url.searchParams.get("page_size")));
        const items = p === 99 ? [] : [tile(`${p}a`), tile(`${p}b`)];
        const body = {
          items,
          page: p,
          page_size: Number(url.searchParams.get("page_size")),
          total: 6,
          pages: 3,
          next_page: p < 3 ? p + 1 : null,
          notice: { code: "option_ignored", message: "note" },
        };
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("page 1: fetches page 1 with page_size 60, shows a pager", async () => {
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    expect(pages).toEqual([1]);
    expect(sizes[0]).toBe(60);
    const combo = screen.getAllByRole("combobox", { name: "Page" })[0];
    expect((combo as HTMLSelectElement).value).toBe("1");
    expect(screen.queryByRole("button", { name: /load more/i })).toBeNull();
  });

  it("?page=2 loads page 2", async () => {
    history.replaceState({}, "", "/see-all?source=stash_images&page=2");
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    expect(pages[0]).toBe(2);
    const combo = screen.getAllByRole("combobox", { name: "Page" })[0];
    expect((combo as HTMLSelectElement).value).toBe("2");
  });

  it("Next pushes ?page=2", async () => {
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    const nextBtn = screen.getAllByRole("button", { name: "Next page" })[0];
    await fireEvent.click(nextBtn);
    await vi.waitFor(() => {
      expect(location.search).toContain("page=2");
    });
    expect(pages).toContain(2);
  });

  it("past-end page is replaced with the served page", async () => {
    served = () => 3;
    history.replaceState({}, "", "/see-all?source=stash_images&page=9");
    render(App);
    await vi.waitFor(() => {
      expect(location.search).toContain("page=3");
      expect(location.search).not.toContain("page=9");
    });
    expect(pages).toEqual([9]);
  });

  it("empty page keeps the pager", async () => {
    served = () => 99;
    history.replaceState({}, "", "/see-all?source=stash_images?page=1");
    render(App);
    await vi.waitFor(() => {
      expect(screen.getByText("Nothing here.")).toBeTruthy();
    });
    expect(screen.getAllByRole("button", { name: "Previous page" })[0]).toBeTruthy();
  });
});
