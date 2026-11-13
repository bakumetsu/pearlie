import { describe, it, expect } from "vitest";
import { tagToString, stringToTag, parseTagInput, addTags, removeTag } from "./tags";

describe("tagToString", () => {
  it("joins scope and name with a colon", () => {
    expect(tagToString({ name: "foo", scope: "artist" })).toBe("artist:foo");
  });

  it("returns just the name when scope is null or absent", () => {
    expect(tagToString({ name: "bar", scope: null })).toBe("bar");
    expect(tagToString({ name: "baz" })).toBe("baz");
  });
});

describe("stringToTag", () => {
  it("splits on the first colon when both sides are non-empty", () => {
    expect(stringToTag("artist:foo")).toEqual({ name: "foo", scope: "artist" });
  });

  it("returns a plain name when there is no colon", () => {
    expect(stringToTag("hello")).toEqual({ name: "hello", scope: null });
  });

  it("treats an empty after-colon as a plain name", () => {
    expect(stringToTag("artist:")).toEqual({ name: "artist:", scope: null });
  });

  it("treats an empty before-colon as a plain name", () => {
    expect(stringToTag(":x")).toEqual({ name: ":x", scope: null });
  });

  it("splits only on the first colon", () => {
    expect(stringToTag("a:b:c")).toEqual({ name: "b:c", scope: "a" });
  });
});

describe("parseTagInput", () => {
  it("splits on whitespace", () => {
    expect(parseTagInput("a b  c,a")).toEqual(["a", "b", "c"]);
  });

  it("splits on commas, trims, drops empties and duplicates (case-insensitive)", () => {
    expect(parseTagInput("a, b,,a")).toEqual(["a", "b"]);
  });

  it("splits on newlines", () => {
    expect(parseTagInput("x\ny\nx")).toEqual(["x", "y"]);
  });

  it("keeps original case", () => {
    expect(parseTagInput("Foo, foo, FOO")).toEqual(["Foo"]);
  });

  it("handles mixed commas and newlines", () => {
    expect(parseTagInput("a, b\nc,,a")).toEqual(["a", "b", "c"]);
  });
});

describe("addTags", () => {
  it("appends new tags case-insensitively", () => {
    expect(addTags(["Alpha"], "beta, ALPHA, gamma")).toEqual(["Alpha", "beta", "gamma"]);
  });

  it("returns the same array instance when nothing is added", () => {
    const arr = ["a", "b"];
    expect(addTags(arr, "A, b")).toBe(arr);
  });

  it("returns a new array when tags are added", () => {
    const arr = ["a"];
    const result = addTags(arr, "b");
    expect(result).not.toBe(arr);
    expect(result).toEqual(["a", "b"]);
  });
});

describe("removeTag", () => {
  it("removes the matching tag and returns a new array", () => {
    expect(removeTag(["a", "b", "c"], "b")).toEqual(["a", "c"]);
  });

  it("returns an equivalent array when the tag is absent", () => {
    const arr = ["a", "b"];
    const result = removeTag(arr, "z");
    expect(result).toEqual(["a", "b"]);
    expect(result).not.toBe(arr);
  });
});
