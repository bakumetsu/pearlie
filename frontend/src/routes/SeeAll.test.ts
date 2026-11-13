// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import seeAllSrc from "./SeeAll.svelte?raw";

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

describe("SeeAll title", () => {
  it("hides an unknown total", () => {
    expect(seeAllSrc).toContain("grid.total != null");
    expect(seeAllSrc).not.toContain('?? "…"');
  });
});
describe("SeeAll paging", () => {
  let pages: number[];
  let sizes: number[];
  let served: (requested: number) => number;
  let vsResponse: { status: number; body: unknown };

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
    vsResponse = { status: 404, body: {} };
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        "http://localhost",
      );
      if (url.pathname === "/api/view-settings") {
        return Promise.resolve(
          new Response(JSON.stringify(vsResponse.body), {
            status: vsResponse.status,
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

  it("stash_videos with modes [wall,list] shows only Wall and List mode buttons", async () => {
    vi.resetModules();
    const { render: freshRender, screen: freshScreen, cleanup: freshCleanup } = await import("@testing-library/svelte");
    const { default: FreshApp } = await import("../App.svelte");
    vsResponse = {
      status: 200,
      body: {
        sources: {
          stash_videos: { mode: "wall", modes: ["wall", "list"], per_page: 60, zoom: 3, per_page_options: [60], per_page_max: 200 },
        },
      },
    };
    history.replaceState({}, "", "/see-all?source=stash_videos");
    freshRender(FreshApp);
    try {
      await freshScreen.findByRole("button", { name: "List" });
      expect(freshScreen.getByRole("button", { name: "Wall" })).toBeTruthy();
      expect(freshScreen.getByRole("button", { name: "List" })).toBeTruthy();
      expect(freshScreen.queryByRole("button", { name: "Grid" })).toBeNull();
      expect(freshScreen.queryByRole("button", { name: "Masonry" })).toBeNull();
    } finally {
      freshCleanup();
    }
  });

  it("komga_series with modes [grid,list] shows only Grid and List mode buttons", async () => {
    vi.resetModules();
    const { render: freshRender, screen: freshScreen, cleanup: freshCleanup } = await import("@testing-library/svelte");
    const { default: FreshApp } = await import("../App.svelte");
    vsResponse = {
      status: 200,
      body: {
        sources: {
          komga_series: { mode: "grid", modes: ["grid", "list"], per_page: 60, zoom: 3, per_page_options: [60], per_page_max: 200 },
        },
      },
    };
    history.replaceState({}, "", "/see-all?source=komga_series");
    freshRender(FreshApp);
    try {
      await freshScreen.findByRole("button", { name: "List" });
      expect(freshScreen.getByRole("button", { name: "Grid" })).toBeTruthy();
      expect(freshScreen.getByRole("button", { name: "List" })).toBeTruthy();
      expect(freshScreen.queryByRole("button", { name: "Wall" })).toBeNull();
      expect(freshScreen.queryByRole("button", { name: "Masonry" })).toBeNull();
    } finally {
      freshCleanup();
    }
  });

  it("stash_images route shows all four mode buttons", async () => {
    vi.resetModules();
    const { render: freshRender, screen: freshScreen, cleanup: freshCleanup } = await import("@testing-library/svelte");
    const { default: FreshApp } = await import("../App.svelte");
    vsResponse = {
      status: 200,
      body: {
        sources: {
          stash_images: { mode: "grid", modes: ["grid", "wall", "masonry", "list"], per_page: 60, zoom: 3, per_page_options: [20, 40, 60, 100, 200], per_page_max: 200 },
        },
      },
    };
    history.replaceState({}, "", "/see-all?source=stash_images");
    freshRender(FreshApp);
    try {
      await freshScreen.findByRole("button", { name: "List" });
      expect(freshScreen.getByRole("button", { name: "Grid" })).toBeTruthy();
      expect(freshScreen.getByRole("button", { name: "Wall" })).toBeTruthy();
      expect(freshScreen.getByRole("button", { name: "Masonry" })).toBeTruthy();
      expect(freshScreen.getByRole("button", { name: "List" })).toBeTruthy();
    } finally {
      freshCleanup();
    }
  });

  it("paging 1 -> 3 adds no history entries", async () => {
    history.replaceState({ depth: 0 }, "", "/");
    history.pushState({ depth: 1 }, "", "/see-all?source=stash_images");
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    const push = vi.spyOn(history, "pushState");
    const rep = vi.spyOn(history, "replaceState");
    const len = history.length;
    await fireEvent.click(screen.getAllByRole("button", { name: "Next page" })[0]);
    await vi.waitFor(() => {
      expect(location.search).toContain("page=2");
    });
    await fireEvent.click(screen.getAllByRole("button", { name: "Next page" })[0]);
    await vi.waitFor(() => {
      expect(location.search).toContain("page=3");
    });
    expect(push).not.toHaveBeenCalled();
    expect(rep).toHaveBeenCalled();
    expect(history.length).toBe(len);
    push.mockRestore();
    rep.mockRestore();
  });

  it("one Back after paging 1 -> 3 leaves See-all for browse", async () => {
    history.replaceState({ depth: 0 }, "", "/");
    history.pushState({ depth: 1 }, "", "/see-all?source=stash_images");
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    await fireEvent.click(screen.getAllByRole("button", { name: "Next page" })[0]);
    await vi.waitFor(() => {
      expect(location.search).toContain("page=2");
    });
    await fireEvent.click(screen.getAllByRole("button", { name: "Next page" })[0]);
    await vi.waitFor(() => {
      expect(location.search).toContain("page=3");
    });
    history.back();
    await vi.waitFor(() => {
      expect(location.pathname).toBe("/");
    });
  });

  it("ArrowRight and ArrowLeft replace the entry", async () => {
    history.replaceState({ depth: 0 }, "", "/");
    history.pushState({ depth: 1 }, "", "/see-all?source=stash_images");
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    const push = vi.spyOn(history, "pushState");
    const rep = vi.spyOn(history, "replaceState");
    const len = history.length;
    await fireEvent.keyDown(window, { key: "ArrowRight" });
    await vi.waitFor(() => {
      expect(location.search).toContain("page=2");
    });
    await fireEvent.keyDown(window, { key: "ArrowLeft" });
    await vi.waitFor(() => {
      expect(location.search).not.toContain("page=");
    });
    expect(push).not.toHaveBeenCalled();
    expect(rep).toHaveBeenCalled();
    expect(history.length).toBe(len);
    push.mockRestore();
    rep.mockRestore();
  });

  it("top and bottom pager carry the spaced class", async () => {
    history.replaceState({ depth: 0 }, "", "/");
    history.pushState({ depth: 1 }, "", "/see-all?source=stash_images");
    const { container } = render(App);
    await vi.waitFor(() => {
      expect(container.querySelectorAll("a.tile").length).toBe(2);
    });
    expect(container.querySelectorAll(".pager-wrap.spaced").length).toBe(2);
  });
});
