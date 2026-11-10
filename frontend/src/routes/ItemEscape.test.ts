// Item page: Escape resets zoom first, leaves the item only when not zoomed (T-47).
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

describe("Item Escape key (T-47)", () => {
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
      const detailMatch = url.pathname.match(/^\/api\/library\/images\/(.+)$/);
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

  it("zoomed image: Escape resets zoom, stays on same item", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);

    const btn = await screen.findByRole("button", { name: "Actual size" });
    await fireEvent.click(btn);
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Fit to screen" })).toBeTruthy();
    });

    fireEvent.keyDown(window, { key: "Escape" });

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Actual size" })).toBeTruthy();
    });
    expect(location.pathname).toBe("/item/images/1b");
  });

  it("not zoomed: Escape navigates away from item", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);

    fireEvent.keyDown(window, { key: "Escape" });

    await vi.waitFor(() => {
      expect(location.pathname).not.toBe("/item/images/1b");
    });
  });

  it("zoomed: ArrowRight still navigates and resets zoom on new item", async () => {
    const { container } = render(App);
    await navigateToItem1b(container);

    const btn = await screen.findByRole("button", { name: "Actual size" });
    await fireEvent.click(btn);
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Fit to screen" })).toBeTruthy();
    });

    fireEvent.keyDown(window, { key: "ArrowRight" });

    await vi.waitFor(() => {
      expect(location.pathname).toBe("/item/images/2a");
    });
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Actual size" })).toBeTruthy();
    });
  });
});
