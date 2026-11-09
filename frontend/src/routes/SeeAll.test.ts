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

describe("SeeAll Load more", () => {
  let pages: number[];

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
    history.replaceState({}, "", "/see-all?source=stash_images");
    pages = [];
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        "http://localhost",
      );
      const page = Number(url.searchParams.get("page") ?? "1");
      pages.push(page);
      const body = {
        items: page === 1 ? [tile("1"), tile("2")] : [tile("3")],
        page,
        page_size: 60,
        total: 3,
        next_page: page === 1 ? 2 : null,
        // each response carries a notice, as the real list does for ignored options
        notice: { code: "option_ignored", message: "note" },
      };
      return Promise.resolve(
        new Response(JSON.stringify(body), {
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

  it("appends page 2 and fetches only page 2", async () => {
    const { container } = render(App);
    const btn = await screen.findByRole("button", { name: "Load more" });
    const before = pages.length;
    await fireEvent.click(btn);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(3);
    });
    expect(pages.slice(before)).toEqual([2]);
  });
});
