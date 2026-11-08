import { describe, it, expect } from "vitest";
import {
  DEFAULT_MODE,
  clampPage,
  visiblePages,
  nextPage,
  prevPage,
  stepKey,
  zoneAction,
  preloadPages,
  isCompleted,
  parseMode,
  pageSrc,
} from "./pages";

describe("clampPage", () => {
  it("returns 1 for NaN", () => {
    expect(clampPage(NaN, 5)).toBe(1);
  });
  it("clamps below 1", () => {
    expect(clampPage(0, 5)).toBe(1);
    expect(clampPage(-3, 5)).toBe(1);
  });
  it("clamps above count", () => {
    expect(clampPage(6, 5)).toBe(5);
  });
  it("treats count 0 as max 1", () => {
    expect(clampPage(3, 0)).toBe(1);
  });
  it("passes through a valid page", () => {
    expect(clampPage(3, 5)).toBe(3);
  });
});

describe("visiblePages", () => {
  it("single mode returns [page]", () => {
    expect(visiblePages(3, 5, false)).toEqual([3]);
  });
  it("spread: cover is shown alone", () => {
    expect(visiblePages(1, 7, true)).toEqual([1]);
    expect(visiblePages(1, 8, true)).toEqual([1]);
  });
  it("spread pairs for count 7", () => {
    expect(visiblePages(2, 7, true)).toEqual([2, 3]);
    expect(visiblePages(3, 7, true)).toEqual([2, 3]);
    expect(visiblePages(4, 7, true)).toEqual([4, 5]);
    expect(visiblePages(5, 7, true)).toEqual([4, 5]);
    expect(visiblePages(6, 7, true)).toEqual([6, 7]);
    expect(visiblePages(7, 7, true)).toEqual([6, 7]);
  });
  it("spread pairs for count 8 (last unpaired)", () => {
    expect(visiblePages(2, 8, true)).toEqual([2, 3]);
    expect(visiblePages(4, 8, true)).toEqual([4, 5]);
    expect(visiblePages(6, 8, true)).toEqual([6, 7]);
    expect(visiblePages(7, 8, true)).toEqual([6, 7]);
    expect(visiblePages(8, 8, true)).toEqual([8]);
  });
  it("clamps page before computing", () => {
    expect(visiblePages(0, 3, false)).toEqual([1]);
    expect(visiblePages(10, 3, false)).toEqual([3]);
  });
});

describe("nextPage", () => {
  it("returns next page in single mode", () => {
    expect(nextPage(1, 5, false)).toBe(2);
    expect(nextPage(3, 5, false)).toBe(4);
  });
  it("returns null at the end (single)", () => {
    expect(nextPage(5, 5, false)).toBeNull();
  });
  it("returns page after spread group", () => {
    expect(nextPage(1, 5, true)).toBe(2);
    expect(nextPage(2, 5, true)).toBe(4);
    expect(nextPage(3, 5, true)).toBe(4);
  });
  it("returns null when group ends at count (spread)", () => {
    expect(nextPage(7, 7, true)).toBeNull();
    expect(nextPage(6, 7, true)).toBeNull();
    expect(nextPage(8, 8, true)).toBeNull();
  });
});

describe("prevPage", () => {
  it("returns 1 at the start (single)", () => {
    expect(prevPage(1, 5, false)).toBe(1);
  });
  it("returns previous page (single)", () => {
    expect(prevPage(3, 5, false)).toBe(2);
  });
  it("returns 1 from cover or first pair (spread)", () => {
    expect(prevPage(1, 5, true)).toBe(1);
    expect(prevPage(2, 5, true)).toBe(1);
    expect(prevPage(3, 5, true)).toBe(1);
  });
  it("returns start of previous pair (spread)", () => {
    expect(prevPage(4, 7, true)).toBe(2);
    expect(prevPage(5, 7, true)).toBe(2);
    expect(prevPage(6, 7, true)).toBe(4);
    expect(prevPage(7, 7, true)).toBe(4);
  });
  it("unpaired last page: previous pair start (spread)", () => {
    expect(prevPage(8, 8, true)).toBe(6);
  });
});

describe("stepKey", () => {
  it("ArrowRight -> next (ltr)", () => {
    expect(stepKey("ArrowRight", false)).toBe("next");
  });
  it("ArrowRight -> prev (rtl swap)", () => {
    expect(stepKey("ArrowRight", true)).toBe("prev");
  });
  it("ArrowLeft -> prev (ltr)", () => {
    expect(stepKey("ArrowLeft", false)).toBe("prev");
  });
  it("ArrowLeft -> next (rtl swap)", () => {
    expect(stepKey("ArrowLeft", true)).toBe("next");
  });
  it("Home -> first regardless of rtl", () => {
    expect(stepKey("Home", false)).toBe("first");
    expect(stepKey("Home", true)).toBe("first");
  });
  it("End -> last regardless of rtl", () => {
    expect(stepKey("End", false)).toBe("last");
    expect(stepKey("End", true)).toBe("last");
  });
  it("other keys -> null", () => {
    expect(stepKey("a", false)).toBeNull();
    expect(stepKey(" ", true)).toBeNull();
    expect(stepKey("Tab", false)).toBeNull();
  });
});

describe("zoneAction", () => {
  it("x=29, w=100 (left 30%) -> prev", () => {
    expect(zoneAction(29, 100, false)).toBe("prev");
  });
  it("x=30, w=100 (boundary) -> toggle", () => {
    expect(zoneAction(30, 100, false)).toBe("toggle");
  });
  it("x=70, w=100 (boundary) -> toggle", () => {
    expect(zoneAction(70, 100, false)).toBe("toggle");
  });
  it("x=71, w=100 (right 30%) -> next", () => {
    expect(zoneAction(71, 100, false)).toBe("next");
  });
  it("rtl swaps prev/next", () => {
    expect(zoneAction(29, 100, true)).toBe("next");
    expect(zoneAction(71, 100, true)).toBe("prev");
  });
  it("centre stays toggle regardless of rtl", () => {
    expect(zoneAction(50, 100, true)).toBe("toggle");
  });
});

describe("preloadPages", () => {
  it("two pages after group (single)", () => {
    expect(preloadPages(1, 5, false)).toEqual([2, 3]);
  });
  it("clips to one page at end (single)", () => {
    expect(preloadPages(2, 3, false)).toEqual([3]);
  });
  it("empty at end (single)", () => {
    expect(preloadPages(3, 3, false)).toEqual([]);
  });
  it("two pages after spread group", () => {
    expect(preloadPages(1, 7, true)).toEqual([2, 3]);
    expect(preloadPages(2, 7, true)).toEqual([4, 5]);
  });
  it("clips at end (spread)", () => {
    expect(preloadPages(6, 7, true)).toEqual([]);
    expect(preloadPages(4, 7, true)).toEqual([6, 7]);
  });
});

describe("isCompleted", () => {
  it("true when page >= count > 0", () => {
    expect(isCompleted(5, 5)).toBe(true);
    expect(isCompleted(6, 5)).toBe(true);
  });
  it("false when page < count", () => {
    expect(isCompleted(4, 5)).toBe(false);
  });
  it("false when count is 0", () => {
    expect(isCompleted(0, 0)).toBe(false);
    expect(isCompleted(1, 0)).toBe(false);
  });
});

describe("parseMode", () => {
  it("null -> DEFAULT_MODE", () => {
    expect(parseMode(null)).toEqual(DEFAULT_MODE);
  });
  it("garbage string -> DEFAULT_MODE", () => {
    expect(parseMode("not json at all")).toEqual(DEFAULT_MODE);
  });
  it("JSON array (not object) -> DEFAULT_MODE", () => {
    expect(parseMode("[1,2,3]")).toEqual(DEFAULT_MODE);
  });
  it("valid full JSON", () => {
    expect(parseMode('{"spread":true,"rtl":true,"fit":"width"}')).toEqual({
      spread: true,
      rtl: true,
      fit: "width",
    });
  });
  it("partial JSON fills missing fields with defaults", () => {
    expect(parseMode('{"spread":true}')).toEqual({
      spread: true,
      rtl: false,
      fit: "height",
    });
    expect(parseMode('{"fit":"width"}')).toEqual({
      spread: false,
      rtl: false,
      fit: "width",
    });
  });
  it("wrong-type fields fall back per field", () => {
    expect(parseMode('{"spread":"yes","rtl":true,"fit":"diagonal"}')).toEqual({
      spread: false,
      rtl: true,
      fit: "height",
    });
  });
});

describe("pageSrc", () => {
  it("replaces {n} with the page number", () => {
    expect(pageSrc("/x/pages/{n}", 7)).toBe("/x/pages/7");
  });
});

