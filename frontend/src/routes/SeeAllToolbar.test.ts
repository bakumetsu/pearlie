// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";
import toolbarSrc from "../lib/browse/Toolbar.svelte?raw";
import sheetSrc from "../lib/browse/FilterSheet.svelte?raw";
import seeAllSrc from "./SeeAll.svelte?raw";

function web(id: string) {
  return { source: "danbooru", post_id: id, title: `post ${id}`, thumb_url: `/t/${id}`, preview_url: `/p/${id}`, width: 100, height: 100, tags: [] };
}

let n = 0; // the grid store outlives a test: a fresh query per test avoids adopting the last one

describe("SeeAll toolbar", () => {
  let searches: URLSearchParams[];
  let lists: URLSearchParams[];
  let caps: Record<string, unknown> | null;
  let filtersMode: "ok" | "fail" | "hold";
  let sectionNotice: unknown;
  let sectionError: unknown;
  let sectionEmpty: boolean;

  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    const obs = class {
      observe() {}
      disconnect() {}
      unobserve() {}
    };
    vi.stubGlobal("IntersectionObserver", obs);
    vi.stubGlobal("ResizeObserver", obs);
    window.scrollTo = vi.fn();
    Object.defineProperty(window, "innerWidth", { value: 1024, configurable: true, writable: true });
    n += 1;
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}`);
    searches = [];
    lists = [];
    caps = { danbooru: { order: ["newest", "score"], rating: ["g", "s", "q", "e"], order_blocked_when: null } };
    filtersMode = "ok";
    sectionNotice = null;
    sectionError = null;
    sectionEmpty = false;
    const json = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      if (url.pathname === "/api/view-settings") return json({}, 404);
      if (url.pathname === "/api/search/filters") {
        if (filtersMode === "hold") return new Promise(() => {});
        return filtersMode === "fail" ? json({}, 500) : json({ sources: caps });
      }
      if (url.pathname === "/api/search") {
        searches.push(url.searchParams);
        return json({ sections: [{ id: "danbooru", items: sectionEmpty ? [] : [web("1"), web("2")], next_page: null, page_size: 60, notice: sectionNotice, error: sectionError }] });
      }
      if (url.pathname.startsWith("/api/library/")) {
        lists.push(url.searchParams);
        return json({ items: [], page: 1, page_size: 60, total: 0, pages: 1, next_page: null });
      }
      return json({});
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function ready(toolbar = true) {
    const r = render(App);
    await vi.waitFor(() => expect(r.container.querySelectorAll(".tile.web").length).toBe(2));
    if (toolbar) await vi.waitFor(() => expect(screen.queryByRole("combobox", { name: "Order" }) ?? screen.queryByRole("button", { name: "Filters" })).not.toBeNull());
    return r;
  }

  it("shows N shown for a web list with no total", async () => {
    await ready();
    expect(screen.getByTestId("shown").textContent).toBe("2 shown");
  });

  it("desktop: Order select is one request with order=score", async () => {
    await ready();
    expect(searches.length).toBe(1);
    expect(searches[0].has("order")).toBe(false);
    const sel = screen.getByRole("combobox", { name: "Order" }) as HTMLSelectElement;
    await fireEvent.change(sel, { target: { value: "score" } });
    await vi.waitFor(() => expect(searches.length).toBe(2));
    expect(searches[1].get("order")).toBe("score");
    expect(location.search).toContain("order=score");
  });

  it("desktop: Rating checkboxes commit one request each and send a csv", async () => {
    await ready();
    await fireEvent.click(screen.getByRole("button", { name: "Rating" }));
    await fireEvent.click(screen.getByRole("checkbox", { name: "Sensitive" }));
    await vi.waitFor(() => expect(searches.length).toBe(2));
    await fireEvent.click(screen.getByRole("checkbox", { name: "General" }));
    await vi.waitFor(() => expect(searches.length).toBe(3));
    expect(searches[2].get("rating")).toBe("g,s");
    expect(location.search).toContain("rating=g%2Cs");
  });

  it("chips show active filters and a tap removes one (one request)", async () => {
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}&order=score&rating=g,s`);
    await ready();
    expect(searches[0].get("order")).toBe("score");
    expect(searches[0].get("rating")).toBe("g,s");
    await fireEvent.click(screen.getByRole("button", { name: "Remove General" }));
    await vi.waitFor(() => expect(searches.length).toBe(2));
    expect(searches[1].get("rating")).toBe("s");
    expect(screen.queryByRole("button", { name: "Remove General" })).toBeNull();
  });

  it("phone: sheet batches changes into one request on Apply", async () => {
    Object.defineProperty(window, "innerWidth", { value: 400, configurable: true, writable: true });
    await ready();
    expect(screen.queryByRole("combobox", { name: "Order" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    await fireEvent.click(screen.getByRole("button", { name: "Top score" }));
    await fireEvent.click(screen.getByRole("button", { name: "Explicit" }));
    await fireEvent.click(screen.getByRole("button", { name: "General" }));
    expect(searches.length).toBe(1);
    await fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(searches.length).toBe(2));
    expect(searches[1].get("order")).toBe("score");
    expect(searches[1].get("rating")).toBe("g,e");
    expect(screen.getByTestId("filter-badge").textContent).toBe("2");
    expect(screen.queryByRole("dialog", { name: "Filters" })).toBeNull();
  });

  it("phone: Apply with nothing changed sends nothing", async () => {
    Object.defineProperty(window, "innerWidth", { value: 400, configurable: true, writable: true });
    await ready();
    await fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    await fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await new Promise((r) => setTimeout(r, 30));
    expect(searches.length).toBe(1);
  });

  it("library keeps Sort and Favorites, no Order/Rating", async () => {
    history.replaceState({}, "", `/library/stash/images?q=lib${n}`);
    render(App);
    await vi.waitFor(() => expect(lists.length).toBe(1));
    expect(screen.getByRole("combobox", { name: "Sort" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Favorites/ })).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Order" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rating" })).toBeNull();
    expect(lists[0].has("order")).toBe(false);
  });

  it("desktop: Order is disabled with a hint once the words reach order_blocked_when", async () => {
    caps = { danbooru: { order: ["newest", "score"], rating: ["g", "s", "q", "e"], order_blocked_when: 2 } };
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}+dog`);
    await ready();
    await vi.waitFor(() => expect((screen.getByRole("combobox", { name: "Order" }) as HTMLSelectElement).disabled).toBe(true));
    expect(screen.getByRole("combobox", { name: "Order" }).closest("label")?.getAttribute("title")).toMatch(/tag limit/);
  });

  it("Order stays enabled below order_blocked_when", async () => {
    caps = { danbooru: { order: ["newest", "score"], rating: ["g", "s", "q", "e"], order_blocked_when: 2 } };
    await ready();
    await vi.waitFor(() => expect(searches.length).toBe(1));
    await new Promise((r) => setTimeout(r, 30));
    expect((screen.getByRole("combobox", { name: "Order" }) as HTMLSelectElement).disabled).toBe(false);
  });

  it("rating options come from the site's list (no Sensitive)", async () => {
    caps = { danbooru: { order: ["newest", "score"], rating: ["g", "q", "e"], order_blocked_when: null } };
    await ready();
    await vi.waitFor(async () => {
      if (!screen.queryByRole("group", { name: "Rating" })) await fireEvent.click(screen.getByRole("button", { name: "Rating" }));
      expect(screen.queryByRole("checkbox", { name: "Sensitive" })).toBeNull();
      expect(screen.getByRole("checkbox", { name: "Questionable" })).toBeTruthy();
    });
  });

  it("hides the toolbar when the site lists no order or rating", async () => {
    caps = { danbooru: { order: [], rating: [] } };
    await ready(false);
    await vi.waitFor(() => expect(screen.queryByRole("combobox", { name: "Order" })).toBeNull());
    expect(screen.queryByRole("button", { name: "Rating" })).toBeNull();
  });

  it("shows no filter controls while /api/search/filters is loading", async () => {
    filtersMode = "hold";
    await ready(false);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("combobox", { name: "Order" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rating" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Filters" })).toBeNull();
    expect(searches.length).toBe(1);
  });

  it("hides the toolbar and keeps the plain list when /api/search/filters fails", async () => {
    filtersMode = "fail";
    await ready(false);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("combobox", { name: "Order" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rating" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Filters" })).toBeNull();
    expect(screen.getByTestId("shown").textContent).toBe("2 shown");
  });

  it("shows the section's filter_notice", async () => {
    sectionNotice = { code: "filter_notice", message: "Rating filtered on this page only" };
    const { container } = await ready();
    expect(container.querySelector("p.notice")?.textContent).toBe("Rating filtered on this page only");
  });

  it("a failed section shows the error with Retry, not Nothing here", async () => {
    sectionError = { code: "upstream_error", message: "Danbooru is down" };
    sectionEmpty = true;
    render(App);
    expect(await screen.findByText(/Danbooru is down/)).toBeTruthy();
    expect(screen.queryByText("Nothing here.")).toBeNull();
    sectionError = null;
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await vi.waitFor(() => expect(screen.getByText("Nothing here.")).toBeTruthy());
  });

  it("filter_dropped shows as a notice next to the results", async () => {
    sectionError = { code: "filter_dropped", message: "Ignored: dog (Danbooru allows 2 tags)" };
    const { container } = await ready();
    expect(container.querySelector("p.notice")?.textContent).toContain("Ignored: dog");
  });

  it("Rating menu closes on outside click and Escape, focus back to the button", async () => {
    await ready();
    const btn = screen.getByRole("button", { name: "Rating" });
    await fireEvent.click(btn);
    expect(screen.queryByRole("group", { name: "Rating" })).not.toBeNull();
    await fireEvent.pointerDown(document.body);
    await vi.waitFor(() => expect(screen.queryByRole("group", { name: "Rating" })).toBeNull());
    await fireEvent.click(btn);
    expect(screen.queryByRole("group", { name: "Rating" })).not.toBeNull();
    await fireEvent.keyDown(document.body, { key: "Escape" });
    await vi.waitFor(() => expect(screen.queryByRole("group", { name: "Rating" })).toBeNull());
    expect(document.activeElement).toBe(btn);
  });

  it("blocked Order sends no order=score and shows no Top score chip", async () => {
    caps = { danbooru: { order: ["newest", "score"], rating: ["g", "s", "q", "e"], order_blocked_when: 2 } };
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}+dog&order=score`);
    await ready();
    await vi.waitFor(() => expect((screen.getByRole("combobox", { name: "Order" }) as HTMLSelectElement).disabled).toBe(true));
    await vi.waitFor(() => expect(searches.length).toBeGreaterThan(0));
    expect(searches[searches.length - 1].has("order")).toBe(false);
    expect(screen.queryByRole("button", { name: "Remove Top score" })).toBeNull();
  });

  it("ignores an order or rating the site does not list", async () => {
    caps = { danbooru: { order: ["newest"], rating: ["g", "q"], order_blocked_when: null } };
    history.replaceState({}, "", `/see-all?source=danbooru&q=cat${n}&order=score&rating=g,s`);
    await ready(false);
    await vi.waitFor(() => expect(searches.length).toBeGreaterThan(1));
    const last = searches[searches.length - 1];
    expect(last.has("order")).toBe(false);
    expect(last.get("rating")).toBe("g");
  });

  it("desktop: Order, Rating, Per page, modes and Zoom share one row", async () => {
    await ready();
    const rows = document.querySelectorAll(".controls");
    expect(rows.length).toBe(1);
    const row = rows[0];
    for (const name of ["Order", "Per page"]) expect(row.querySelector(`[aria-label="${name}"]`)).toBeTruthy();
    for (const name of ["Rating", "Grid", "Zoom"]) expect(row.querySelector(`[aria-label="${name}"]`)).toBeTruthy();
  });

  it("header hides on scroll down, shows on scroll up and on focus", async () => {
    await ready();
    const header = document.querySelector(".sticky-header") as HTMLElement;
    const scrollTo = async (y: number) => {
      Object.defineProperty(window, "scrollY", { value: y, configurable: true, writable: true });
      await fireEvent.scroll(window);
    };
    await scrollTo(600);
    await scrollTo(700);
    expect(header.classList.contains("hidden")).toBe(true);
    await scrollTo(650);
    expect(header.classList.contains("hidden")).toBe(false);
    await scrollTo(800);
    expect(header.classList.contains("hidden")).toBe(true);
    await fireEvent.focusIn(header);
    expect(header.classList.contains("hidden")).toBe(false);
    await scrollTo(0);
  });

  it("header stays visible while the Rating menu is open", async () => {
    await ready();
    const header = document.querySelector(".sticky-header") as HTMLElement;
    await fireEvent.click(screen.getByRole("button", { name: "Rating" }));
    Object.defineProperty(window, "scrollY", { value: 900, configurable: true, writable: true });
    await fireEvent.scroll(window);
    expect(header.classList.contains("hidden")).toBe(false);
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true, writable: true });
  });

  it("touch targets are at least 44px", () => {
    expect(toolbarSrc).toContain("min-height: 44px");
    expect(sheetSrc.match(/min-height: 44px/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it("phone keeps a wrapping toolbar row; nowrap only from 640px", () => {
    expect(seeAllSrc).toMatch(/\.controls \{[^}]*flex-wrap: wrap;/);
    expect(seeAllSrc).toMatch(/@media \(min-width: 640px\) \{ \.controls \{ flex-wrap: nowrap; \} \}/);
  });
});
