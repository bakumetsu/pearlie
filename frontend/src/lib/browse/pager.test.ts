import { describe, it, expect } from "vitest";
import {
  rangeText,
  pagerForm,
  pageOptions,
  pagerState,
  remapPage,
  clampInput,
  pageOf,
} from "./pager";

describe("rangeText", () => {
  it("returns full string with stats and total", () => {
    const result = rangeText({
      page: 5,
      perPage: 20,
      shown: 40,
      total: 757,
      stats: { megapixels: 5149, size_bytes: 3435973836 },
    });
    expect(result).toBe("81-120 of 757 (5,149 Megapixels - 3.2 GiB)");
  });

  it("returns total without stats", () => {
    const result = rangeText({
      page: 1,
      perPage: 50,
      shown: 50,
      total: 250,
      stats: null,
    });
    expect(result).toBe("1-50 of 250");
  });

  it("returns range only when total is null", () => {
    const result = rangeText({
      page: 1,
      perPage: 50,
      shown: 50,
      total: null,
      stats: null,
    });
    expect(result).toBe("1-50");
  });

  it("returns empty string when shown is 0", () => {
    const result = rangeText({
      page: 1,
      perPage: 50,
      shown: 0,
      total: 250,
      stats: null,
    });
    expect(result).toBe("");
  });

  it("includes hidden count in shown", () => {
    const result = rangeText({
      page: 2,
      perPage: 20,
      shown: 22,
      total: 100,
      stats: null,
    });
    expect(result).toBe("21-42 of 100");
  });

  it("drops null megapixels part", () => {
    const result = rangeText({
      page: 1,
      perPage: 10,
      shown: 10,
      total: 50,
      stats: { megapixels: null, size_bytes: 1073741824 },
    });
    expect(result).toBe("1-10 of 50 (1.0 GiB)");
  });

  it("drops null size_bytes part", () => {
    const result = rangeText({
      page: 1,
      perPage: 10,
      shown: 10,
      total: 50,
      stats: { megapixels: 5000, size_bytes: null },
    });
    expect(result).toBe("1-10 of 50 (5,000 Megapixels)");
  });

  it("appends nothing when both stats parts are null", () => {
    const result = rangeText({
      page: 1,
      perPage: 10,
      shown: 10,
      total: 50,
      stats: { megapixels: null, size_bytes: null },
    });
    expect(result).toBe("1-10 of 50");
  });

  it("formats megapixels with thousands separators", () => {
    const result = rangeText({
      page: 1,
      perPage: 10,
      shown: 10,
      total: null,
      stats: { megapixels: 1234567, size_bytes: null },
    });
    expect(result).toBe("1-10 (1,234,567 Megapixels)");
  });

  it("formats GiB with one decimal", () => {
    const result = rangeText({
      page: 1,
      perPage: 10,
      shown: 10,
      total: null,
      stats: { megapixels: null, size_bytes: 2147483648 },
    });
    expect(result).toBe("1-10 (2.0 GiB)");
  });
});

describe("pagerForm", () => {
  it("returns full for a number", () => {
    expect(pagerForm(10)).toBe("full");
  });

  it("returns reduced for null", () => {
    expect(pagerForm(null)).toBe("reduced");
  });
});

describe("pageOptions", () => {
  it("returns select at 200", () => {
    const result = pageOptions(200);
    expect(result).toEqual({
      kind: "select",
      values: Array.from({ length: 200 }, (_, i) => i + 1),
    });
  });

  it("returns field at 201", () => {
    expect(pageOptions(201)).toEqual({ kind: "field" });
  });
});

describe("pagerState", () => {
  it("full form, first page", () => {
    expect(pagerState({ page: 1, pages: 10, hasNext: true })).toEqual({
      first: false,
      prev: false,
      next: true,
      last: true,
      showLast: true,
    });
  });

  it("full form, last page", () => {
    expect(pagerState({ page: 10, pages: 10, hasNext: false })).toEqual({
      first: true,
      prev: true,
      next: false,
      last: false,
      showLast: true,
    });
  });

  it("reduced form, hasNext true", () => {
    expect(pagerState({ page: 3, pages: null, hasNext: true })).toEqual({
      first: true,
      prev: true,
      next: true,
      last: false,
      showLast: false,
    });
  });

  it("reduced form, hasNext false", () => {
    expect(pagerState({ page: 3, pages: null, hasNext: false })).toEqual({
      first: true,
      prev: true,
      next: false,
      last: false,
      showLast: false,
    });
  });
});

describe("remapPage", () => {
  it("page 3 of 40/per-page gives first index 81, remap to 20 per page gives 5", () => {
    expect(remapPage(81, 20)).toBe(5);
  });

  it("first index 1 gives page 1", () => {
    expect(remapPage(1, 20)).toBe(1);
  });
});

describe("clampInput", () => {
  it("valid value", () => {
    expect(clampInput("40", 100)).toBe(40);
  });

  it("zero is below minimum", () => {
    expect(clampInput("0", 100)).toBeNull();
  });

  it("value above cap", () => {
    expect(clampInput("101", 100)).toBeNull();
  });

  it("non-digit suffix", () => {
    expect(clampInput("12a", 100)).toBeNull();
  });

  it("trims surrounding whitespace", () => {
    expect(clampInput(" 7 ", 100)).toBe(7);
  });

  it("empty string", () => {
    expect(clampInput("", 100)).toBeNull();
  });
});

describe("pageOf", () => {
  it("parses valid page number", () => {
    expect(pageOf("5")).toBe(5);
  });

  it("returns 1 for zero", () => {
    expect(pageOf("0")).toBe(1);
  });

  it("returns 1 for null", () => {
    expect(pageOf(null)).toBe(1);
  });

  it("returns 1 for non-numeric", () => {
    expect(pageOf("abc")).toBe(1);
  });

  it("returns 1 for non-integer", () => {
    expect(pageOf("3.7")).toBe(1);
  });

  it("returns 1 for negative", () => {
    expect(pageOf("-1")).toBe(1);
  });
});
