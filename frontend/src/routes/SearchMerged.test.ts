// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent, screen } from "@testing-library/svelte";
import App from "../App.svelte";

const OPTIONS = {
  sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, profile: "desktop",
  backdrop_strength: 60, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true,
  allow_blurred_tags: false, trash_retention_days: 7, images_per_site: 10, stump_scan_wait_s: 10,
  source_pace: {}, tapped_first: false, hidden_sites: [], site_order: ["danbooru", "gelbooru", "rule34", "nhentai"],
};

function post(source: string, i: number) {
  return { source, post_id: String(i), thumb_url: `/t/${i}`, preview_url: `/p/${i}`, media_kind: "image", title: `${source} ${i}`, tags: [], target: "stash", saveable: true, owned: false };
}

describe("Discover merged row wiring", () => {
  let searches: string[][];
  let merged: number;
  let store: Map<string, string>;

  beforeEach(() => {
    store = new Map();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: () => {},
      clear: () => {},
    });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/");
    searches = [];
    merged = 0;
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      let body: unknown = { sections: [] };
      if (url.pathname === "/api/search") {
        const sources = (url.searchParams.get("sources") ?? "").split(",");
        searches.push(sources);
        body = { sections: sources.map((id) => ({ id, title: id, items: [] })) };
      } else if (url.pathname === "/api/discover/merged") {
        merged++;
        body = { items: [post("danbooru", 1), post("gelbooru", 2)], sites: [{ id: "danbooru", state: "ok" }, { id: "gelbooru", state: "ok" }], hidden: 0, pending: false };
      } else if (url.pathname === "/api/options") {
        body = OPTIONS;
      }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const settle = () => new Promise((r) => setTimeout(r, 450));

  it("first visit: All is on first, the merged row shows, no library or site search call", async () => {
    const { container } = render(App);
    await settle();
    const marks = screen.getByRole("group", { name: "Sites" }).querySelectorAll("button");
    expect(marks[0].getAttribute("aria-label")).toBe("All");
    expect(marks[0].getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Latest from your sites")).toBeTruthy();
    expect(container.querySelectorAll(".site-badge").length).toBe(2);
    expect(merged).toBe(1);
    expect(searches).toEqual([]);
  });

  it("a site tap turns All off: one row per site, and no library rows on an empty query", async () => {
    render(App);
    await settle();
    await fireEvent.click(screen.getByRole("button", { name: "Gelbooru" }));
    await settle();
    expect(screen.getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("false");
    expect(searches).toEqual([["gelbooru"]]);
    expect(store.get("pearlie.search.all")).toBe("0");
    expect(screen.queryByText("Latest from your sites")).toBeNull();
  });

  it("a device that only remembers sites keeps them (no All)", async () => {
    store.set("pearlie.search.sites", "danbooru");
    render(App);
    await settle();
    expect(screen.getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("false");
    expect(merged).toBe(0);
    expect(searches).toEqual([["danbooru"]]);
  });
});
