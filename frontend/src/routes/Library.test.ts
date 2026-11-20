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
    const stumpBtn = within(group).getByRole("button", { name: "Stump" });

    expect(allBtn.getAttribute("aria-pressed")).toBe("true");
    expect(stashBtn).toBeTruthy();
    expect(stumpBtn).toBeTruthy();

    await vi.waitFor(() => {
      expect(recordedUrls.some((u) => u.includes("/api/library/stash/images"))).toBe(true);
      expect(recordedUrls.some((u) => u.includes("/api/library/stash/videos"))).toBe(true);
      expect(recordedUrls.some((u) => u.includes("/api/library/stump/series"))).toBe(true);
      expect(recordedUrls.some((u) => u.includes("/api/library/stump/books"))).toBe(false);
    });
  });

  it("requests 28 items per section row", async () => {
    render(App);

    await vi.waitFor(() => {
      const rowUrls = recordedUrls.filter((u) => u.includes("/api/library/"));
      expect(rowUrls.length).toBeGreaterThanOrEqual(3);
      for (const u of rowUrls) expect(u).toContain("page_size=28");
    });
  });

  it("clicking Stump sets pressed state, persists hub, and swaps fetches", async () => {
    render(App);

    const group = screen.getByRole("group", { name: "Source" });
    const stumpBtn = within(group).getByRole("button", { name: "Stump" });

    await vi.waitFor(() => {
      expect(recordedUrls.some((u) => u.includes("/api/library/stash/images"))).toBe(true);
    });

    recordedUrls.length = 0;
    await fireEvent.click(stumpBtn);

    expect(stumpBtn.getAttribute("aria-pressed")).toBe("true");
    expect(store["pearlie.library.hub"]).toBe("stump");

    await vi.waitFor(() => {
      expect(recordedUrls.some((u) => u.includes("/stump/series"))).toBe(true);
    });
    expect(recordedUrls.some((u) => u.includes("/stash/"))).toBe(false);

    expect(screen.queryByRole("heading", { name: "Images" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Videos" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Books" })).toBeTruthy();
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
    expect(recordedUrls.some((u) => u.includes("/stump/"))).toBe(false);
  });
});

describe("Library Random chip", () => {
  let recordedUrls: string[];

  beforeEach(() => {
    history.replaceState({}, "", "/library");
    recordedUrls = [];
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      recordedUrls.push(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      return Promise.resolve(
        new Response(JSON.stringify({ items: [], page: 1, page_size: 28, total: 0, next_page: null }), {
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

  it("sits between All and Favorites and shuffles with a seed kept in the URL", async () => {
    render(App);
    const group = screen.getByRole("group", { name: "Filter" });
    const names = within(group).getAllByRole("button").map((b) => b.textContent?.trim());
    expect(names.slice(0, 3)).toEqual(["All", "Random", "Favorites"]);

    await fireEvent.click(within(group).getByRole("button", { name: "Random" }));
    await vi.waitFor(() => {
      const params = new URLSearchParams(location.search);
      expect(params.get("sort")).toBe("random");
      expect(params.get("seed")).toMatch(/^\d+$/);
      expect(recordedUrls.some((u) => u.includes("sort=random") && u.includes("seed="))).toBe(true);
    });
    expect(within(group).getByRole("button", { name: "Random" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(group).getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("See all keeps sort=random and the same seed", async () => {
    history.replaceState({}, "", "/library?sort=random&seed=4242");
    render(App);
    await vi.waitFor(() => {
      const links = screen.getAllByRole("link", { name: "See all" });
      expect(links.length).toBeGreaterThan(0);
      for (const a of links) expect(a.getAttribute("href")).toMatch(/\?sort=random&seed=4242$/);
    });
  });

  it("All clears sort and seed", async () => {
    history.replaceState({}, "", "/library?sort=random&seed=4242");
    render(App);
    const group = screen.getByRole("group", { name: "Filter" });
    await fireEvent.click(within(group).getByRole("button", { name: "All" }));
    await vi.waitFor(() => expect(location.search).toBe(""));
  });
});
