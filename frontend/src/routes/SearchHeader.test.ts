// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import App from "../App.svelte";
import { filterChips, DEFAULT_SITES, toggleSiteIn } from "../lib/query";

function mockMedia(matching: string[]) {
  vi.stubGlobal(
    "matchMedia",
    (q: string) => ({
      matches: matching.includes(q),
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

describe("filterChips", () => {
  const base = { chips: [], pill: "all" as const, sites: DEFAULT_SITES };

  it("is empty for the defaults", () => {
    expect(filterChips(base)).toEqual([]);
  });

  it("lists a non-default scope and sites, each with its clearing change", () => {
    const chips = filterChips({ ...base, pill: "images", sites: ["danbooru", "nhentai"] });
    expect(chips.map((c) => c.label)).toEqual(["Images", "Danbooru", "nhentai"]);
    expect(chips[0].remove).toEqual({ pill: "all" });
    expect(chips[2].remove).toEqual({ sites: ["danbooru"] });
  });

  it("shows No sites that resets to the default", () => {
    const chips = filterChips({ ...base, sites: [] });
    expect(chips).toHaveLength(1);
    expect(chips[0].remove).toEqual({ sites: DEFAULT_SITES });
  });

  it("toggleSiteIn keeps the canonical order", () => {
    expect(toggleSiteIn(["nhentai"], "danbooru")).toEqual(["danbooru", "nhentai"]);
  });
});

describe("Discover header", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/?q=cat");
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ sections: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("names only the active site mark", async () => {
    render(App);
    const marks = screen.getByRole("group", { name: "Sites" });
    expect(within(marks).getByRole("button", { name: "Danbooru" }).textContent).toContain("Danbooru");
    // inactive marks show the letter only; the name stays in aria-label
    expect(within(marks).getByRole("button", { name: "Gelbooru" }).textContent?.trim()).toBe("G");
  });

  it("hides the chips row at defaults and shows it when filters are set", async () => {
    render(App);
    expect(screen.queryByRole("group", { name: "Active filters" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Gelbooru" }));
    const row = await screen.findByRole("group", { name: "Active filters" });
    expect(within(row).getByRole("button", { name: "Remove Gelbooru" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Filters (2 set)" })).toBeTruthy();
    await fireEvent.click(within(row).getByRole("button", { name: "Remove Gelbooru" }));
    expect(screen.queryByRole("group", { name: "Active filters" })).toBeNull();
  });

  it("opens and closes the filter panel with an equal 2-column grid", async () => {
    render(App);
    expect(screen.queryByRole("dialog", { name: "Filters" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    const panel = screen.getByRole("dialog", { name: "Filters" });
    const scope = within(panel).getByTestId("scope-opts");
    const sites = within(panel).getByTestId("site-opts");
    expect(scope.querySelectorAll("button")).toHaveLength(5);
    expect(sites.querySelectorAll("button")).toHaveLength(4);
    const src = (await import("../lib/components/FilterPanel.svelte?raw")).default as string;
    expect(src).toMatch(/grid-template-columns:\s*1fr 1fr/);

    await fireEvent.click(within(panel).getByRole("button", { name: "Images" }));
    expect(screen.getByRole("group", { name: "Active filters" })).toBeTruthy();
    await fireEvent.click(within(panel).getByRole("button", { name: "Clear all" }));
    expect(screen.queryByRole("group", { name: "Active filters" })).toBeNull();

    await fireEvent.click(within(panel).getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog", { name: "Filters" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Filters" })).toBeNull();
  });

  it("uses the bottom bar layout on a portrait phone", async () => {
    mockMedia(["(max-width: 719px)"]);
    const { container } = render(App);
    const page = container.querySelector(".page")!;
    expect(page.classList.contains("phone")).toBe(true);
    expect(page.classList.contains("landscape")).toBe(false);
  });

  it("uses the landscape layout when the height is short", async () => {
    mockMedia(["(max-width: 719px)", "(max-height: 500px)"]);
    const { container } = render(App);
    const page = container.querySelector(".page")!;
    expect(page.classList.contains("landscape")).toBe(true);
    expect(page.classList.contains("phone")).toBe(false);
  });

  it("uses neither class on a desktop screen", async () => {
    mockMedia([]);
    const { container } = render(App);
    const page = container.querySelector(".page")!;
    expect(page.classList.contains("phone")).toBe(false);
    expect(page.classList.contains("landscape")).toBe(false);
  });
});
