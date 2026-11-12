// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import SiteMarks from "./SiteMarks.svelte";
import { effectiveSites } from "../query";

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
