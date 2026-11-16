import { describe, it, expect, vi } from "vitest";
import { parseWeb, withWeb, webTileHref, fetchWebPost, webKey } from "./webOpen";
import { parseOpen, withOpen } from "./overlayState";

const q = (s: string) => new URLSearchParams(s);

describe("parseWeb", () => {
  it("reads source and post id", () => {
    expect(parseWeb(q("web=danbooru:123"))).toEqual({ source: "danbooru", postId: "123" });
  });
  it("rejects missing, malformed, unknown site and non-numeric id", () => {
    expect(parseWeb(q(""))).toBeNull();
    expect(parseWeb(q("web=danbooru"))).toBeNull();
    expect(parseWeb(q("web=danbooru:"))).toBeNull();
    expect(parseWeb(q("web=danbooru:1a"))).toBeNull();
    expect(parseWeb(q("web=nhentai:12"))).toBeNull();
    expect(parseWeb(q("web=evil:12"))).toBeNull();
  });
});

describe("withWeb", () => {
  it("sets and clears the param and keeps the others", () => {
    expect(withWeb(q("q=cat&page=2"), "gelbooru:9")).toBe("q=cat&page=2&web=gelbooru%3A9");
    expect(withWeb(q("q=cat&web=gelbooru%3A9"), null)).toBe("q=cat");
  });
  it("drops an invalid key", () => {
    expect(withWeb(q("q=cat&web=danbooru%3A1"), "danbooru:x")).toBe("q=cat");
  });
  it("leaves the library open param alone", () => {
    const s = withWeb(q("open=image%3A5"), "danbooru:7");
    expect(parseOpen(q(s))).toBe("5");
    expect(parseWeb(q(s))?.postId).toBe("7");
    expect(parseWeb(q(withOpen(q(s), null)))?.postId).toBe("7");
  });
});

describe("webTileHref", () => {
  it("links a booru tile to the current page with the param", () => {
    expect(webTileHref("/see-all", q("source=danbooru&q=cat"), { source: "danbooru", post_id: "5" })).toBe(
      "/see-all?source=danbooru&q=cat&web=danbooru%3A5",
    );
  });
  it("gives no href for nhentai", () => {
    expect(webTileHref("/", q(""), { source: "nhentai", post_id: "5" })).toBeUndefined();
  });
});

describe("fetchWebPost", () => {
  const item = { source: "danbooru", post_id: "5", thumb_url: "", preview_url: "", width: 1, height: 1 };
  it("searches by id limited to the site and returns the match", async () => {
    const search = vi.fn().mockResolvedValue({ query: "id:5", sections: [{ id: "danbooru", title: "D", items: [item], hidden: 0 }] });
    const got = await fetchWebPost({ search }, { source: "danbooru", postId: "5" });
    expect(search).toHaveBeenCalledWith({ q: "id:5", sources: ["danbooru"], page: 1, page_size: 1 }, undefined);
    expect(got).toBe(item);
    expect(webKey("danbooru", "5")).toBe("danbooru:5");
  });
  it("returns null when hidden or on error", async () => {
    const empty = vi.fn().mockResolvedValue({ query: "id:5", sections: [{ id: "danbooru", title: "D", items: [], hidden: 1 }] });
    expect(await fetchWebPost({ search: empty }, { source: "danbooru", postId: "5" })).toBeNull();
    const bad = vi.fn().mockRejectedValue(new Error("x"));
    expect(await fetchWebPost({ search: bad }, { source: "danbooru", postId: "5" })).toBeNull();
  });
});
