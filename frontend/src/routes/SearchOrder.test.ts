// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";

const OPTIONS = {
  sfw: false,
  sfw_set: true,
  player_rate: 1,
  player_rate_set: true,
  profile: "desktop",
  backdrop_strength: 60,
  backdrop_wall: true,
  backdrop_item: true,
  backdrop_lightbox: true,
  allow_blurred_tags: false,
  trash_retention_days: 7,
  source_pace: {},
  hidden_sites: [],
  site_order: ["gelbooru", "danbooru", "rule34", "nhentai"],
};

describe("Discover site order", () => {
  let searches: { sources: string[] }[];
  let puts: unknown[];
  let saved: typeof OPTIONS;

  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/?q=cat&src=web&sites=danbooru,gelbooru");
    searches = [];
    puts = [];
    saved = OPTIONS;
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      let body: unknown = { sections: [] };
      if (url.pathname === "/api/search") {
        const sources = (url.searchParams.get("sources") ?? "").split(",");
        searches.push({ sources });
        body = { sections: sources.map((id) => ({ id, error: { code: "x", message: "off" } })) };
      } else if (url.pathname === "/api/options") {
        if (init?.method === "PUT") {
          puts.push(JSON.parse(String(init.body)));
          saved = { ...saved, ...puts[puts.length - 1] as object };
        }
        body = saved;
      }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const settle = () => new Promise((r) => setTimeout(r, 450));

  it("runs the site rows in the saved order, and a reorder saves once without a new search", async () => {
    render(App);
    await settle();
    const rows = () => Array.from(document.querySelectorAll("h2")).map((h) => h.textContent?.trim());
    expect(rows().filter((t) => t === "gelbooru" || t === "danbooru")).toEqual(["gelbooru", "danbooru"]);
    const before = searches.length;

    await fireEvent.keyDown(screen.getByRole("button", { name: "Danbooru" }), { key: "ArrowLeft", altKey: true });
    await settle();
    expect(puts).toEqual([{ site_order: ["danbooru", "gelbooru", "rule34", "nhentai"] }]);
    expect(searches.length).toBe(before);
    expect(rows().filter((t) => t === "gelbooru" || t === "danbooru")).toEqual(["danbooru", "gelbooru"]);
  });
});
