// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { vi } from "vitest";
import { render, screen, cleanup, fireEvent, within, waitFor } from "@testing-library/svelte";
import SiteMarks from "./SiteMarks.svelte";
import { effectiveSites, orderedSites, moveSite } from "../query";

afterEach(cleanup);

describe("SiteMarks", () => {
  it("shows the backend icon for each site", () => {
    const { container } = render(SiteMarks, { sites: ["danbooru"], onsites: () => {} });
    const imgs = Array.from(container.querySelectorAll("img")).map((i) => i.getAttribute("src"));
    expect(imgs).toEqual([
      "/api/site-icons/danbooru",
      "/api/site-icons/gelbooru",
      "/api/site-icons/rule34",
      "/api/site-icons/nhentai",
    ]);
  });

  it("marks site icons data-sfw-shown", () => {
    const { container } = render(SiteMarks, { sites: [], onsites: () => {} });
    const imgs = container.querySelectorAll("img");
    expect(imgs.length).toBeGreaterThan(0);
    imgs.forEach((img) => {
      expect(img.getAttribute("data-sfw-shown")).toBe("1");
    });
  });

  it("falls back to the letter when the icon fails", async () => {
    const { container } = render(SiteMarks, { sites: [], onsites: () => {} });
    const btn = screen.getByRole("button", { name: "Gelbooru" });
    await fireEvent.error(btn.querySelector("img")!);
    expect(btn.querySelector("img")).toBeNull();
    expect(btn.textContent?.trim()).toBe("G");
    expect(container.querySelectorAll("img")).toHaveLength(3);
  });

  it("leaves a hidden site out of the rail", () => {
    render(SiteMarks, { sites: ["danbooru"], onsites: () => {}, hidden: ["gelbooru", "rule34"] });
    const marks = screen.getByRole("group", { name: "Sites" });
    expect(within(marks).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Danbooru",
      "nhentai",
    ]);
  });
});

describe("effectiveSites", () => {
  it("drops hidden sites", () => {
    expect(effectiveSites(["danbooru", "nhentai"], ["nhentai"])).toEqual(["danbooru"]);
  });

  it("moves a hidden active site to the first visible one", () => {
    expect(effectiveSites(["danbooru"], ["danbooru"])).toEqual(["gelbooru"]);
    expect(effectiveSites(["danbooru"], ["danbooru", "gelbooru"])).toEqual(["rule34"]);
  });

  it("keeps an empty selection and handles everything hidden", () => {
    expect(effectiveSites([], ["danbooru"])).toEqual([]);
    expect(effectiveSites(["danbooru"], ["danbooru", "gelbooru", "rule34", "nhentai"])).toEqual([]);
  });
});

describe("orderedSites / moveSite", () => {
  it("appends unknown sites and drops invalid names", () => {
    expect(orderedSites(["rule34", "bogus", "rule34", "danbooru"])).toEqual(["rule34", "danbooru", "gelbooru", "nhentai"]);
    expect(orderedSites(undefined)).toEqual(["danbooru", "gelbooru", "rule34", "nhentai"]);
  });

  it("moves a site to where another sits", () => {
    const o = orderedSites(undefined);
    expect(moveSite(o, "nhentai", "danbooru")).toEqual(["nhentai", "danbooru", "gelbooru", "rule34"]);
    expect(moveSite(o, "danbooru", "rule34")).toEqual(["gelbooru", "rule34", "danbooru", "nhentai"]);
    expect(moveSite(o, "danbooru", "danbooru")).toEqual(o);
  });
});

describe("SiteMarks reorder", () => {
  const names = () =>
    within(screen.getByRole("group", { name: "Sites" }))
      .getAllByRole("button")
      .map((b) => b.getAttribute("aria-label"));

  // jsdom has no layout: each pill is 50 px wide, in rail order.
  function layout() {
    const btns = Array.from(document.querySelectorAll<HTMLElement>("[data-site]"));
    btns.forEach((b, i) => {
      b.getBoundingClientRect = () => ({ left: i * 50, right: i * 50 + 50, top: 0, bottom: 44, width: 50, height: 44, x: i * 50, y: 0, toJSON() {} }) as DOMRect;
    });
  }
  const ptr = (type: string, x: number, pointerType: string) => {
    const e = new Event(type, { bubbles: true }) as Event & Record<string, unknown>;
    Object.assign(e, { clientX: x, clientY: 10, pointerType, button: 0 });
    window.dispatchEvent(e);
  };
  const down = (el: Element, x: number, pointerType: string) =>
    fireEvent(el, Object.assign(new Event("pointerdown", { bubbles: true }), { clientX: x, clientY: 10, pointerType, button: 0 }));

  it("follows the saved order", () => {
    render(SiteMarks, { sites: [], onsites: () => {}, order: ["rule34", "danbooru"] });
    expect(names()).toEqual(["Rule34", "Danbooru", "Gelbooru", "nhentai"]);
  });

  it("drags with the mouse and saves once on release", async () => {
    const onreorder = vi.fn();
    const onsites = vi.fn();
    render(SiteMarks, { sites: [], onsites, onreorder });
    layout();
    await down(screen.getByRole("button", { name: "Danbooru" }), 25, "mouse");
    ptr("pointermove", 60, "mouse");
    ptr("pointermove", 125, "mouse");
    expect(onreorder).not.toHaveBeenCalled();
    ptr("pointerup", 125, "mouse");
    expect(onreorder).toHaveBeenCalledTimes(1);
    expect(onreorder).toHaveBeenCalledWith(["gelbooru", "rule34", "danbooru", "nhentai"]);
    // The click that ends a drag does not toggle the site
    await fireEvent.click(screen.getByRole("button", { name: "Danbooru" }));
    expect(onsites).not.toHaveBeenCalled();
  });

  it("a drag released off the rail does not eat the next click", async () => {
    const onsites = vi.fn();
    render(SiteMarks, { sites: [], onsites, onreorder: () => {} });
    layout();
    await down(screen.getByRole("button", { name: "Danbooru" }), 25, "mouse");
    ptr("pointermove", 125, "mouse");
    ptr("pointerup", 900, "mouse");
    await new Promise((r) => setTimeout(r, 5));
    await fireEvent.click(screen.getByRole("button", { name: "Rule34" }));
    expect(onsites).toHaveBeenCalledWith(["rule34"]);
  });

  it("a tap still selects and saves no order", async () => {
    const onreorder = vi.fn();
    const onsites = vi.fn();
    render(SiteMarks, { sites: [], onsites, onreorder });
    layout();
    const b = screen.getByRole("button", { name: "Gelbooru" });
    await down(b, 75, "touch");
    ptr("pointerup", 75, "touch");
    await fireEvent.click(b);
    expect(onsites).toHaveBeenCalledWith(["gelbooru"]);
    expect(onreorder).not.toHaveBeenCalled();
  });

  it("a touch drag starts only after a long press", async () => {
    vi.useFakeTimers();
    try {
      const onreorder = vi.fn();
      render(SiteMarks, { sites: [], onsites: () => {}, onreorder });
      layout();
      // Moving before the hold is a scroll
      await down(screen.getByRole("button", { name: "Danbooru" }), 25, "touch");
      ptr("pointermove", 125, "touch");
      vi.advanceTimersByTime(500);
      ptr("pointerup", 125, "touch");
      expect(onreorder).not.toHaveBeenCalled();
      // Hold, then drag
      await down(screen.getByRole("button", { name: "Danbooru" }), 25, "touch");
      vi.advanceTimersByTime(500);
      ptr("pointermove", 125, "touch");
      ptr("pointerup", 125, "touch");
      expect(onreorder).toHaveBeenCalledWith(["gelbooru", "rule34", "danbooru", "nhentai"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reorders from the keyboard with Alt+arrow, skipping hidden sites in the move", async () => {
    const onreorder = vi.fn();
    render(SiteMarks, { sites: [], onsites: () => {}, onreorder, hidden: ["gelbooru"] });
    const b = screen.getByRole("button", { name: "Danbooru" });
    await fireEvent.keyDown(b, { key: "ArrowRight" });
    expect(onreorder).not.toHaveBeenCalled();
    await fireEvent.keyDown(b, { key: "ArrowRight", altKey: true });
    // Hidden Gelbooru keeps its place: Danbooru lands where Rule34 sat
    expect(onreorder).toHaveBeenCalledWith(["gelbooru", "rule34", "danbooru", "nhentai"]);
    await waitFor(() => expect(document.activeElement).toBe(b));
  });

  it("does not drag when no reorder handler is given", async () => {
    render(SiteMarks, { sites: [], onsites: () => {} });
    layout();
    await down(screen.getByRole("button", { name: "Danbooru" }), 25, "mouse");
    ptr("pointermove", 125, "mouse");
    expect(names()).toEqual(["Danbooru", "Gelbooru", "Rule34", "nhentai"]);
  });
});
