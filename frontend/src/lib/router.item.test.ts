import { describe, it, expect } from "vitest";
import { matchRoute } from "./router";

describe("item and read routes", () => {
  it("matches /item/videos/12", () => {
    const m = matchRoute("/item/videos/12", "");
    expect(m.name).toBe("item");
    expect(m.params).toEqual({ kinds: "videos", id: "12" });
  });

  it("decodes percent-encoded id in /item/series/s%201", () => {
    const m = matchRoute("/item/series/s%201", "");
    expect(m.name).toBe("item");
    expect(m.params).toEqual({ kinds: "series", id: "s 1" });
  });

  it("matches /read/b7 with query", () => {
    const m = matchRoute("/read/b7", "?p=3");
    expect(m.name).toBe("read");
    expect(m.params).toEqual({ bookId: "b7" });
    expect(m.query.get("p")).toBe("3");
  });

  it("matches /read/web/nhentai/123 as read-web, not as a Komga book", () => {
    const m = matchRoute("/read/web/nhentai/123", "?p=4");
    expect(m.name).toBe("read-web");
    expect(m.params).toEqual({ source: "nhentai", id: "123" });
    expect(m.query.get("p")).toBe("4");
  });

  it("matches /web/nhentai/123 as web-book", () => {
    const m = matchRoute("/web/nhentai/123", "");
    expect(m.name).toBe("web-book");
    expect(m.params).toEqual({ source: "nhentai", id: "123" });
  });

  it("returns not_found for /item/images (missing id)", () => {
    const m = matchRoute("/item/images", "");
    expect(m.name).toBe("not_found");
  });
});
