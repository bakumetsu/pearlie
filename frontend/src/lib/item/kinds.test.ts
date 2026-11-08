import { describe, it, expect } from "vitest";
import { toPlural, toSingular, itemHref, itemKey } from "./kinds";

describe("toPlural", () => {
  it("returns plural forms unchanged", () => {
    expect(toPlural("images")).toBe("images");
    expect(toPlural("videos")).toBe("videos");
    expect(toPlural("series")).toBe("series");
    expect(toPlural("books")).toBe("books");
  });

  it("converts singular to plural", () => {
    expect(toPlural("image")).toBe("images");
    expect(toPlural("video")).toBe("videos");
    expect(toPlural("book")).toBe("books");
  });

  it("returns null for unknown input", () => {
    expect(toPlural("movies")).toBeNull();
    expect(toPlural("")).toBeNull();
    expect(toPlural("IMAGE")).toBeNull();
  });
});

describe("toSingular", () => {
  it("maps each Kind to its SingularKind", () => {
    expect(toSingular("images")).toBe("image");
    expect(toSingular("videos")).toBe("video");
    expect(toSingular("series")).toBe("series");
    expect(toSingular("books")).toBe("book");
  });
});

describe("itemHref", () => {
  it("builds the URL with the plural kind and encoded id", () => {
    expect(itemHref({ kind: "image", id: "42" })).toBe("/item/images/42");
    expect(itemHref({ kind: "video", id: "a b" })).toBe("/item/videos/a%20b");
    expect(itemHref({ kind: "series", id: "s1" })).toBe("/item/series/s1");
    expect(itemHref({ kind: "book", id: "b/1" })).toBe("/item/books/b%2F1");
  });
});

describe("itemKey", () => {
  it("returns kind:id", () => {
    expect(itemKey({ kind: "book", id: "x" })).toBe("book:x");
    expect(itemKey({ kind: "image", id: "001" })).toBe("image:001");
  });
});
