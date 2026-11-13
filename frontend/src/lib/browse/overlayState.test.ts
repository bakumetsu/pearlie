// @vitest-environment jsdom
// overlayState tests

import { describe, it, expect } from "vitest";
import { parseOpen, openKey, withOpen, findTile } from "./overlayState";

describe("parseOpen", () => {
  it("returns id for valid image key", () => {
    const q = new URLSearchParams("open=image:abc");
    expect(parseOpen(q)).toBe("abc");
  });

  it("returns null when open param is missing", () => {
    const q = new URLSearchParams("page=1");
    expect(parseOpen(q)).toBeNull();
  });

  it("returns null for invalid values", () => {
    expect(parseOpen(new URLSearchParams("open=video:1"))).toBeNull();
    expect(parseOpen(new URLSearchParams("open=image:"))).toBeNull();
    expect(parseOpen(new URLSearchParams("open=image:a:b"))).toBeNull();
    expect(parseOpen(new URLSearchParams("open=abc"))).toBeNull();
    expect(parseOpen(new URLSearchParams("open=image:a%20b"))).toBeNull();
  });
});

describe("openKey", () => {
  it("returns image:<id>", () => {
    expect(openKey("abc")).toBe("image:abc");
  });
});

describe("withOpen", () => {
  it("adds open and preserves other params", () => {
    const q = new URLSearchParams("page=2&q=x");
    const result = withOpen(q, "image:foo");
    const parsed = new URLSearchParams(result);
    expect(parsed.get("open")).toBe("image:foo");
    expect(parsed.get("page")).toBe("2");
    expect(parsed.get("q")).toBe("x");
  });

  it("removes open when key is null", () => {
    const q = new URLSearchParams("open=image:old&page=2");
    const result = withOpen(q, null);
    const parsed = new URLSearchParams(result);
    expect(parsed.get("open")).toBeNull();
    expect(parsed.get("page")).toBe("2");
  });

  it("rejects non-image key (does not add open)", () => {
    const q = new URLSearchParams("page=2");
    const result = withOpen(q, "video:1");
    const parsed = new URLSearchParams(result);
    expect(parsed.get("open")).toBeNull();
  });

  it("does not mutate input", () => {
    const q = new URLSearchParams("open=image:old&page=2");
    withOpen(q, "image:new");
    expect(q.get("open")).toBe("image:old");
    expect(q.get("page")).toBe("2");
  });

  it("removes open for an image-prefixed but invalid key", () => {
    for (const key of ["image:", "image:a:b", "image:a b"]) {
      const result = withOpen(new URLSearchParams("open=image:old&page=2"), key);
      expect(result).toBe("page=2");
    }
  });
});

describe("findTile", () => {
  it("finds a tile whose id has quotes or brackets without throwing", () => {
    document.body.innerHTML = `<div data-key="image:a">x</div><div id="t"></div>`;
    const t = document.getElementById("t")!;
    t.setAttribute("data-key", 'image:a"b]c');
    const id = parseOpen(new URLSearchParams({ open: 'image:a"b]c' }))!;
    expect(findTile(document, openKey(id))).toBe(t);
    expect(findTile(document, "image:missing")).toBeNull();
  });
});
