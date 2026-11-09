// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import App from "../App.svelte";

describe("Library hub chips", () => {
  let recordedUrls: string[];
  let store: Record<string, string>;

  beforeEach(() => {
    store = {};
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { store = {}; },
    });
    history.replaceState({}, "", "/library");
    recordedUrls = [];
    globalThis.fetch = vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        recordedUrls.push(url);
        return Promise.resolve(
          new Response(
            JSON.stringify({ items: [], page: 1, page_size: 12, total: 0, next_page: null }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      },
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("defaults to All with all four source fetches fired", async () => {
    render(App);

    const group = screen.getByRole("group", { name: "Source" });
    const allBtn = within(group).getByRole("button", { name: "All" });
    const stashBtn = within(group).getByRole("button", { name: "Stash" });
    const komgaBtn = within(group).getByRole("button", { name: "Komga" });

    expect(allBtn.getAttribute("aria-pressed")).toBe("true");
    expect(stashBtn).toBeTruthy();
    expect(komgaBtn).toBeTruthy();

    await vi.waitFor(() => {
      expect(recordedUrls.some((u) => u.includes("/api/library/stash/images"))).toBe(true);
      expect(recordedUrls.some((u) => u.includes("/api/library/stash/videos"))).toBe(true);
      expect(recordedUrls.some((u) => u.includes("/api/library/komga/series"))).toBe(true);
      expect(recordedUrls.some((u) => u.includes("/api/library/komga/books"))).toBe(true);
    });
  });

  it("clicking Komga sets pressed state, persists hub, and swaps fetches", async () => {
    render(App);

    const group = screen.getByRole("group", { name: "Source" });
    const komgaBtn = within(group).getByRole("button", { name: "Komga" });

    await vi.waitFor(() => {
      expect(recordedUrls.some((u) => u.includes("/api/library/stash/images"))).toBe(true);
    });

    recordedUrls.length = 0;
    await fireEvent.click(komgaBtn);

    expect(komgaBtn.getAttribute("aria-pressed")).toBe("true");
    expect(store["pearlie.library.hub"]).toBe("komga");

    await vi.waitFor(() => {
      expect(recordedUrls.some((u) => u.includes("/komga/series"))).toBe(true);
    });
    expect(recordedUrls.some((u) => u.includes("/stash/"))).toBe(false);

    expect(screen.queryByRole("heading", { name: "Images" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Videos" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Series" })).toBeTruthy();
  });

  it("remembers stash from localStorage on render", async () => {
    store["pearlie.library.hub"] = "stash";
    render(App);

    const group = screen.getByRole("group", { name: "Source" });
    const stashBtn = within(group).getByRole("button", { name: "Stash" });
    expect(stashBtn.getAttribute("aria-pressed")).toBe("true");

    await vi.waitFor(() => {
      expect(recordedUrls.length).toBeGreaterThan(0);
    });
    expect(recordedUrls.some((u) => u.includes("/komga/"))).toBe(false);
  });
});
