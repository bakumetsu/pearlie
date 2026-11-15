import { describe, it, expect } from "vitest";
import { firstTapped } from "./tappedSite.svelte";

const SITES = ["danbooru", "gelbooru", "rule34", "nhentai"] as const;

describe("firstTapped", () => {
  it("moves the tapped site to the front and keeps the rest in order", () => {
    expect(firstTapped([...SITES], "rule34", true)).toEqual(["rule34", "danbooru", "gelbooru", "nhentai"]);
  });

  it("keeps the order when off, when nothing was tapped, or when the site is not selected", () => {
    expect(firstTapped([...SITES], "rule34", false)).toEqual([...SITES]);
    expect(firstTapped([...SITES], null, true)).toEqual([...SITES]);
    expect(firstTapped(["danbooru", "gelbooru"], "rule34", true)).toEqual(["danbooru", "gelbooru"]);
  });
});
