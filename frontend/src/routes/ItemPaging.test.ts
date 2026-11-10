// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import { resetAllGrids } from "../lib/stores/shared.svelte";

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

function detail(id: string) {
  return {
    ...tile(id),
    full_url: `/f/${id}`,
    tags: [],
    width: 100,
    height: 100,
  };
}

async function navigateToItem1b(container: HTMLElement) {
  await vi.waitFor(() => {
    expect(container.querySelectorAll("a.tile").length).toBe(2);
  });
  const link = Array.from(container.querySelectorAll("a.tile")).find(
    (a) => a.getAttribute("href") === "/item/images/1b",
  )!;
  await fireEvent.click(link);
  await vi.waitFor(() => {
    expect(location.pathname).toBe("/item/images/1b");
  });
}

describe("Item prev/next across pages", () => {
  let pages: number[];

  beforeEach(() => {
    resetAllGrids();
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
      const detailMatch = url.pathname.match(/^\/api\/library\/stash\/images\/(.+)$/);
      if (detailMatch) {
        const id = detailMatch[1];
        return Promise.resolve(
          new Response(JSON.stringify(detail(id)), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.pathname === "/api/library/stash/images") {
        const p = Number(url.searchParams.get("page") ?? "1");
        pages.push(p);
        const items = [tile(`${p}a`), tile(`${p}b`)];
        const body = {
          items,
          page: p,
          page_size: Number(url.searchParams.get("page_size")),
          total: 6,
          pages: 3,
          next_page: p < 3 ? p + 1 : null,
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

  it("Next at page edge loads page 2 and opens its first item", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);
    const nextBtn = screen.getByRole("button", { name: "Next item" });
    expect(nextBtn).toBeTruthy();
    await fireEvent.click(nextBtn);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/2a");
    });
    expect(pages).toContain(2);
  });

  it("Prev at page edge goes back a page and opens its last item", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);
    const nextBtn = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/2a");
    });
    const prevBtn = screen.getByRole("button", { name: "Previous item" });
    expect(prevBtn).toBeTruthy();
    await fireEvent.click(prevBtn);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/1b");
    });
  });

  it("Prev disabled on the very first item", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);
    const prevBtn = screen.getByRole("button", { name: "Previous item" });
    await fireEvent.click(prevBtn);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/1a");
    });
    const prevBtnAfter = screen.getByRole("button", { name: "Previous item" });
    expect((prevBtnAfter as HTMLButtonElement).disabled).toBe(true);
  });

  it("Back after crossing a page shows the grid's page with no extra fetch", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);
    const nextBtn = screen.getByRole("button", { name: "Next item" });
    await fireEvent.click(nextBtn);
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/2a");
    });
    const fetchCountBefore = pages.length;
    history.back();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/see-all");
      expect(location.search).toContain("page=2");
      const tiles = container.querySelectorAll("a.tile");
      expect(tiles.length).toBe(2);
      const hrefs = Array.from(tiles).map((a) => a.getAttribute("href"));
      expect(hrefs).toContain("/item/images/2a");
      expect(hrefs).toContain("/item/images/2b");
      expect(pages.length).toBe(fetchCountBefore);
    });
  });
});
