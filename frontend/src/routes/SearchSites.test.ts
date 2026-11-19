// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent, screen } from "@testing-library/svelte";
import App from "../App.svelte";

const OPTIONS = {
  sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, profile: "desktop",
  backdrop_strength: 60, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true,
  allow_blurred_tags: false, trash_retention_days: 7, images_per_site: 10, stump_scan_wait_s: 10,
  source_pace: {}, tapped_first: true, hidden_sites: [], site_order: ["danbooru", "gelbooru", "rule34", "nhentai"],
};

describe("Remembered site pills", () => {
  let searches: string[][];
  let store: Map<string, string>;

  beforeEach(() => {
    store = new Map([["pearlie.search.sites", "rule34,gelbooru"]]);
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: () => {},
      clear: () => {},
    });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    searches = [];
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      let body: unknown = { sections: [] };
      if (url.pathname === "/api/search") {
        const sources = (url.searchParams.get("sources") ?? "").split(",");
        searches.push(sources);
        body = { sections: sources.map((id) => ({ id, error: { code: "x", message: "off" } })) };
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

  it("uses the remembered pills when the address has none", async () => {
    history.replaceState({}, "", "/?q=cat&src=web");
    render(App);
    await settle();
    expect([...searches[0]].sort()).toEqual(["gelbooru", "rule34"]);
  });

  it("lets a pill in the address win", async () => {
    history.replaceState({}, "", "/?q=cat&src=web&sites=nhentai");
    render(App);
    await settle();
    expect(searches[0]).toEqual(["nhentai"]);
  });

  it("puts the tapped pill first in the rows but keeps the fixed order in the address and memory", async () => {
    store.set("pearlie.search.sites", "danbooru,gelbooru");
    history.replaceState({}, "", "/?q=cat&src=web");
    render(App);
    await settle();
    const before = searches.length;
    await fireEvent.click(screen.getByRole("button", { name: "Rule34" }));
    await settle();
    // The tap adds a site, so one new search; the rows move with no further call.
    expect(searches.length).toBe(before + 1);
    expect(store.get("pearlie.search.sites")).toBe("danbooru,gelbooru,rule34");
    expect(new URL(location.href).searchParams.get("sites")).toBe("danbooru,gelbooru,rule34");
    expect(searches.at(-1)).toEqual(["rule34", "danbooru", "gelbooru"]);
  });
});
