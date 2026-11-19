// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, cleanup, fireEvent, screen } from "@testing-library/svelte";
import App from "../App.svelte";

const OPTIONS = {
  sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, profile: "desktop",
  backdrop_strength: 60, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true,
  allow_blurred_tags: false, trash_retention_days: 7, images_per_site: 10, stump_scan_wait_s: 10,
  source_pace: {}, tapped_first: true, hidden_sites: ["rule34"], site_order: ["danbooru", "gelbooru", "rule34", "nhentai"],
};

describe("Filter panel sites", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      const body = url.pathname === "/api/options" ? OPTIONS : { sections: [] };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("leaves a site hidden in Options out of the list", async () => {
    history.replaceState({}, "", "/?q=cat&src=web");
    render(App);
    await new Promise((r) => setTimeout(r, 450));
    await fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    const opts = await screen.findByTestId("site-opts");
    const labels = [...opts.querySelectorAll("button")].map((b) => b.textContent);
    expect(labels).toContain("Danbooru");
    expect(labels).not.toContain("Rule34");
  });
});
