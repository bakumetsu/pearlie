// SeeAll + WallOverlay wiring tests (T-65)
// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

function tile(id: string) {
  return {
    kind: "image",
    id,
    title: `img ${id}`,
    thumb_url: `/t/${id}`,
    full_url: `/f/${id}.jpg`,
    favorite: false,
    tags: [],
    rating: null,
    source: "stash",
  };
}

function detail(id: string) {
  return {
    kind: "image",
    id,
    title: `img ${id}`,
    thumb_url: `/t/${id}`,
    full_url: `/f/${id}.jpg`,
    favorite: false,
    tags: [],
    rating: null,
    source: "stash",
  };
}

describe("SeeAll + WallOverlay wiring", () => {
  let pages: number[];
  let detailIds: string[];
  let vsMode: string;
  let failPage: number | null;

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
    Element.prototype.scrollIntoView = vi.fn();
    history.replaceState({}, "", "/see-all?source=stash_images");
    pages = [];
    detailIds = [];
    vsMode = "wall";
    failPage = null;
    globalThis.fetch = vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = new URL(
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url,
          "http://localhost",
        );
        if (url.pathname === "/api/view-settings") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                sources: {
                  stash_images: {
                    mode: vsMode,
                    modes: ["grid", "wall", "masonry", "list"],
                    per_page: 60,
                    zoom: 3,
                    per_page_options: [20, 40, 60, 100, 200],
                    per_page_max: 200,
                  },
                },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        const detailMatch = url.pathname.match(
          /^\/api\/library\/images\/([^/]+)$/,
        );
        if (detailMatch) {
          const id = detailMatch[1];
          detailIds.push(id);
          return Promise.resolve(
            new Response(JSON.stringify(detail(id)), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        if (url.pathname.startsWith("/api/library/")) {
          const requested = Number(url.searchParams.get("page") ?? "1");
          if (failPage !== null && requested === failPage)
            return Promise.resolve(
              new Response(
                JSON.stringify({ error: "boom" }),
                { status: 500, headers: { "Content-Type": "application/json" } },
              ),
            );
          const p = requested;
          pages.push(requested);
          const items = [tile(`${p}a`), tile(`${p}b`)];
          const body = {
            items,
            page: p,
            page_size: Number(url.searchParams.get("page_size") ?? "60"),
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
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("clicking a wall tile pushes open=image:<id> and shows the viewer", async () => {
    vi.resetModules();
    const { render, screen, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState({}, "", "/see-all?source=stash_images");
    const { container } = render(App);

    const tileEl = await waitFor(() => {
      const el = container.querySelector('[data-key="image:1a"]');
      expect(el).not.toBeNull();
      return el as Element;
    });
    fireEvent.click(tileEl);

    await waitFor(() => {
      const s = location.search;
      expect(s.includes("open=image%3A1a") || s.includes("open=image:1a")).toBe(
        true,
      );
    });

    const dialog = screen.getByRole("dialog", { name: "Image viewer" });
    expect(dialog).toBeTruthy();
    expect(dialog.getAttribute("role")).toBe("dialog");

    cleanup();
  });

  it("stale open in grid mode is stripped by replace", async () => {
    vi.resetModules();
    vsMode = "grid";
    const { render, cleanup, waitFor } = await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState(
      {},
      "",
      "/see-all?source=stash_images&open=image:1a",
    );
    render(App);

    await waitFor(() => {
      expect(location.search.includes("open")).toBe(false);
    });

    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).toBeNull();

    cleanup();
  });

  it("reload with open= shows the viewer and Close replaces the URL without open", async () => {
    vi.resetModules();
    const { render, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState(
      {},
      "",
      "/see-all?source=stash_images&open=image:1a",
    );
    render(App);

    await waitFor(() => {
      const d = document.querySelector('[role="dialog"]');
      expect(d).not.toBeNull();
    });

    const closeBtn = document.querySelector('button[aria-label="Close"]');
    expect(closeBtn).not.toBeNull();
    fireEvent.click(closeBtn!);

    await waitFor(() => {
      const d = document.querySelector('[role="dialog"]');
      expect(d).toBeNull();
      expect(location.search.includes("open")).toBe(false);
    });

    cleanup();
  });

  it("Close after a push calls history.back", async () => {
    vi.resetModules();
    const { render, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState({}, "", "/see-all?source=stash_images");
    const { container } = render(App);

    const tileEl = await waitFor(() => {
      const el = container.querySelector('[data-key="image:1a"]');
      expect(el).not.toBeNull();
      return el as Element;
    });
    fireEvent.click(tileEl);

    await waitFor(() => {
      const s = location.search;
      expect(s.includes("open=image%3A1a") || s.includes("open=image:1a")).toBe(
        true,
      );
    });

    const backSpy = vi.spyOn(history, "back");
    const closeBtn = document.querySelector('button[aria-label="Close"]');
    expect(closeBtn).not.toBeNull();
    fireEvent.click(closeBtn!);

    expect(backSpy).toHaveBeenCalledTimes(1);

    cleanup();
  });

  it("close after crossing a page pops the opening entry, then replaces and stays on the new page, last tile focused", async () => {
    vi.resetModules();
    const { render, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState({}, "", "/see-all?source=stash_images");
    const { container } = render(App);

    const tileEl = await waitFor(() => {
      const el = container.querySelector('[data-key="image:1b"]');
      expect(el).not.toBeNull();
      return el as Element;
    });
    fireEvent.click(tileEl);

    await waitFor(() => {
      const d = document.querySelector('[role="dialog"]');
      expect(d).not.toBeNull();
    });

    const back = vi.spyOn(history, "back");

    fireEvent.keyDown(document.querySelector('[role="dialog"]')!, {
      key: "ArrowRight",
    });

    await waitFor(() => {
      const s = location.search;
      expect(s.includes("page=2")).toBe(true);
      expect(s.includes("open=image%3A2a") || s.includes("open=image:2a")).toBe(
        true,
      );
    });

    const fetchedBeforeClose = pages.length;
    const closeBtn = document.querySelector('button[aria-label="Close"]');
    expect(closeBtn).not.toBeNull();
    fireEvent.click(closeBtn!);

    await waitFor(() => {
      const d = document.querySelector('[role="dialog"]');
      expect(d).toBeNull();
      expect(location.search.includes("open")).toBe(false);
      expect(location.search.includes("page=2")).toBe(true);
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(pages.slice(fetchedBeforeClose)).not.toContain(1);

    expect(back).toHaveBeenCalledTimes(1);
    expect(location.search.includes("open")).toBe(false);

    await waitFor(() => {
      expect(document.activeElement?.getAttribute("data-key")).toBe("image:2a");
    });

    // Back after Close does not reopen the overlay
    history.back();
    await new Promise((r) => setTimeout(r, 100));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(location.search.includes("open")).toBe(false);

    cleanup();
  });

  it("failed next page shows an error toast and the viewer stays on the current image", async () => {
    vi.resetModules();
    const { render, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    failPage = 2;
    history.replaceState(
      {},
      "",
      "/see-all?source=stash_images&open=image:1b",
    );
    render(App);

    await waitFor(() => {
      const d = document.querySelector('[role="dialog"]');
      expect(d).not.toBeNull();
    });

    await waitFor(() => {
      expect(document.querySelector('[role="dialog"] select[aria-label="Page"]')).not.toBeNull();
      expect(document.querySelector('[role="dialog"] [aria-busy="false"]')).not.toBeNull();
    });

    fireEvent.keyDown(document.querySelector('[role="dialog"]')!, {
      key: "ArrowRight",
    });

    await waitFor(() => {
      expect(document.body.textContent).toContain("Could not load the next page");
    });

    expect(
      location.search.includes("open=image%3A1b") ||
        location.search.includes("open=image:1b"),
    ).toBe(true);
    expect(location.search).not.toContain("page=2");

    const d = document.querySelector('[role="dialog"]');
    expect(d).not.toBeNull();

    cleanup();
  });

  it("arrow keys with the viewer open do not change the grid page", async () => {
    vi.resetModules();
    const { render, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState(
      {},
      "",
      "/see-all?source=stash_images&open=image:1a",
    );
    render(App);

    await waitFor(() => {
      expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    });

    document.body.focus();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    await new Promise((r) => setTimeout(r, 0));

    expect(pages).not.toContain(2);
    expect(location.search).not.toContain("page=2");

    cleanup();
  });

  it("page jump keeps the viewer open on the first image of the new page", async () => {
    vi.resetModules();
    const { render, cleanup, fireEvent, waitFor } =
      await import("@testing-library/svelte");
    const App = (await import("../App.svelte")).default;

    history.replaceState(
      {},
      "",
      "/see-all?source=stash_images&open=image:1a",
    );
    render(App);

    await waitFor(() => {
      expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    });

    const select = await waitFor(() => {
      const s =
        document.querySelector(
          '[role="dialog"] select[aria-label="Page"]',
        );
      expect(s).not.toBeNull();
      return s as HTMLSelectElement;
    });
    select.value = "2";
    fireEvent.change(select, { target: { value: "2" } });

    await waitFor(() => {
      const s = location.search;
      const hasOpen =
        s.includes("open=image%3A2a") || s.includes("open=image:2a");
      const hasPage = s.includes("page=2");
      expect(hasOpen).toBe(true);
      expect(hasPage).toBe(true);
    });

    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();

    cleanup();
  });
});
