// Item side panel: open/closed state persists in localStorage, responsive default by width (T-53).
// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import itemSrc from "./Item.svelte?raw";

const PANEL_KEY = "pearlie.item.panel";

function detail(id: string) {
  return {
    kind: "image",
    id,
    title: `img ${id}`,
    thumb_url: `/t/${id}`,
    full_url: `/f/${id}`,
    source: "stash",
    tags: [],
    width: 100,
    height: 100,
  };
}

function setWidth(w: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: w,
  });
}

function makeStorage(
  initial?: string,
  opts?: { throwOnGet?: boolean; throwOnSet?: boolean },
) {
  return {
    getItem: vi.fn((key: string) => {
      if (opts?.throwOnGet) throw new Error("localStorage getItem error");
      return key === PANEL_KEY ? initial : null;
    }),
    setItem: vi.fn(() => {
      if (opts?.throwOnSet) throw new Error("localStorage setItem error");
    }),
    removeItem: vi.fn(),
    clear: vi.fn(),
  };
}

async function renderAndWait() {
  const { container } = render(App);
  await vi.waitFor(() => {
    expect(
      container.querySelector(
        'button[aria-label="Hide panel"], button[aria-label="Show panel"]',
      ),
    ).toBeTruthy();
  });
  await vi.waitFor(() => {
    expect(container.querySelector("aside.panel[aria-busy]")).toBeNull();
  });
  return { container };
}

describe("Item side panel (T-53)", () => {
  beforeEach(() => {
    setWidth(1024);
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
    history.replaceState({}, "", "/item/images/1b");
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
            new Response(JSON.stringify({}), {
              status: 404,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        const detailMatch = url.pathname.match(
          /^\/api\/library\/images\/(.+)$/,
        );
        if (detailMatch) {
          const id = detailMatch[1];
          return Promise.resolve(
            new Response(JSON.stringify(detail(id)), {
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
    cleanup();
    vi.unstubAllGlobals();
    setWidth(1024);
  });

  it("desktop 1024, nothing stored: panel open by default", async () => {
    setWidth(1024);
    vi.stubGlobal("localStorage", makeStorage());

    const { container } = await renderAndWait();

    const hideBtn = screen.getByRole("button", { name: "Hide panel" });
    expect(hideBtn.getAttribute("aria-expanded")).toBe("true");
    expect(screen.queryByRole("button", { name: "Show panel" })).toBeNull();

    const panel = container.querySelector("aside.panel")!;
    expect(panel.getAttribute("aria-hidden")).toBe("false");
  });

  it("phone 375, nothing stored: panel collapsed by default", async () => {
    setWidth(375);
    vi.stubGlobal("localStorage", makeStorage());

    const { container } = await renderAndWait();

    const showBtn = screen.getByRole("button", { name: "Show panel" });
    expect(showBtn.getAttribute("aria-expanded")).toBe("false");

    const panel = container.querySelector("aside.panel")!;
    expect(panel.getAttribute("aria-hidden")).toBe("true");

    const body = document.querySelector(".body")!;
    expect(body.classList.contains("collapsed")).toBe(true);
  });

  it("defaults never write to storage", async () => {
    // Render at 1024
    setWidth(1024);
    const storage1 = makeStorage();
    vi.stubGlobal("localStorage", storage1);
    await renderAndWait();
    expect(storage1.setItem).not.toHaveBeenCalled();

    // Clean up first render, set up second at 375
    cleanup();
    setWidth(375);
    const storage2 = makeStorage();
    vi.stubGlobal("localStorage", storage2);
    history.replaceState({}, "", "/item/images/1b");
    await renderAndWait();
    expect(storage2.setItem).not.toHaveBeenCalled();
  });

  it("toggling writes to storage and restores state", async () => {
    setWidth(1024);
    const storage = makeStorage();
    vi.stubGlobal("localStorage", storage);

    const { container } = await renderAndWait();

    // Hide
    const hideBtn = screen.getByRole("button", { name: "Hide panel" });
    await fireEvent.click(hideBtn);

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Show panel" })).toBeTruthy();
    });
    const body = document.querySelector(".body")!;
    expect(body.classList.contains("collapsed")).toBe(true);
    expect(storage.setItem).toHaveBeenCalledTimes(1);
    expect(storage.setItem).toHaveBeenCalledWith(PANEL_KEY, "closed");

    // Show
    const showBtn = screen.getByRole("button", { name: "Show panel" });
    await fireEvent.click(showBtn);

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Hide panel" })).toBeTruthy();
    });
    expect(storage.setItem).toHaveBeenCalledTimes(2);
    expect(storage.setItem).toHaveBeenLastCalledWith(PANEL_KEY, "open");

    const panel = container.querySelector("aside.panel")!;
    expect(panel.getAttribute("aria-hidden")).toBe("false");
  });

  it("stored value wins over width default", async () => {
    // Stored "closed" at 1024 → collapsed
    setWidth(1024);
    vi.stubGlobal("localStorage", makeStorage("closed"));
    await renderAndWait();
    expect(
      screen.getByRole("button", { name: "Show panel" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Hide panel" }),
    ).toBeNull();

    cleanup();
    vi.unstubAllGlobals();
    setWidth(375);
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
    history.replaceState({}, "", "/item/images/1b");

    // Stored "open" at 375 → open
    vi.stubGlobal("localStorage", makeStorage("open"));
    await renderAndWait();
    expect(
      screen.getByRole("button", { name: "Hide panel" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Show panel" }),
    ).toBeNull();
  });

  it("storage that throws on get/set: page renders with width default and toggle works", async () => {
    setWidth(1024);
    vi.stubGlobal(
      "localStorage",
      makeStorage(undefined, { throwOnGet: true, throwOnSet: true }),
    );

    await renderAndWait();

    // Default at 1024 is open
    const hideBtn = screen.getByRole("button", { name: "Hide panel" });
    expect(hideBtn).toBeTruthy();

    // Toggle should still flip state without throwing
    await expect(
      fireEvent.click(hideBtn),
    ).resolves.not.toThrow();

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Show panel" })).toBeTruthy();
    });
  });

  it("Escape on close button: phone collapses panel, desktop navigates away", async () => {
    // Phone 375, stored "open" → panel open; Escape collapses, stays on item
    setWidth(375);
    vi.stubGlobal("localStorage", makeStorage("open"));
    await renderAndWait();

    const closeBtn = screen.getByRole("button", { name: "Hide panel" });
    fireEvent.keyDown(closeBtn, { key: "Escape", bubbles: true });

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Show panel" })).toBeTruthy();
    });
    expect(location.pathname).toBe("/item/images/1b");

    cleanup();
    vi.unstubAllGlobals();

    // Re-stub for desktop scenario
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
    history.replaceState({}, "", "/item/images/1b");

    // Desktop 1024, open → Escape navigates away instead of collapsing
    setWidth(1024);
    vi.stubGlobal("localStorage", makeStorage());
    await renderAndWait();

    const closeBtnDesktop = screen.getByRole("button", {
      name: "Hide panel",
    });
    fireEvent.keyDown(closeBtnDesktop, { key: "Escape", bubbles: true });

    await vi.waitFor(() => {
      expect(location.pathname).not.toBe("/item/images/1b");
    });
  });

  it("handle: near-edge pointermove shows it, far pointermove hides it (T-59)", async () => {
    setWidth(1024);
    vi.stubGlobal("localStorage", makeStorage("closed"));
    await renderAndWait();

    const handle = screen.getByRole("button", { name: "Show panel" });
    expect(handle.classList.contains("near")).toBe(false);

    await fireEvent(window, new MouseEvent("pointermove", { clientX: 1000 }));
    expect(handle.classList.contains("near")).toBe(true);

    await fireEvent(window, new MouseEvent("pointermove", { clientX: 500 }));
    expect(handle.classList.contains("near")).toBe(false);
  });

  it("handle: panel open renders no handle (T-59)", async () => {
    setWidth(1024);
    vi.stubGlobal("localStorage", makeStorage("open"));
    await renderAndWait();

    expect(screen.queryByRole("button", { name: "Show panel" })).toBeNull();
  });

  it("handle: CSS sits above the player, aligned with the panel button, shown on focus (T-59)", () => {
    const rule = itemSrc.match(/\n {2}\.handle \{([^}]*)\}/);
    expect(rule).not.toBeNull();
    const z = rule![1].match(/z-index:\s*(\d+)/);
    expect(z).not.toBeNull();
    expect(Number(z![1])).toBeGreaterThan(21);
    expect(rule![1]).toMatch(/top:\s*var\(--s-4\)/);
    expect(itemSrc).toMatch(/@media \(hover: hover\) and \(pointer: fine\)/);
    expect(itemSrc).toMatch(/\.handle:focus-visible/);
    expect(itemSrc).toMatch(/\.handle\.near/);
  });
});
