import { describe, it, expect } from "vitest";
import { zoomSize, columnCount, dealMasonry, wallRows, fallbackAspect } from "./layout";

describe("zoomSize", () => {
  it("returns table values at zoom 1", () => {
    expect(zoomSize("grid", 1)).toBe(100);
    expect(zoomSize("wall", 1)).toBe(100);
    expect(zoomSize("masonry", 1)).toBe(100);
    expect(zoomSize("list", 1)).toBe(48);
  });
  it("returns table values at zoom 5", () => {
    expect(zoomSize("grid", 5)).toBe(260);
    expect(zoomSize("wall", 5)).toBe(320);
    expect(zoomSize("masonry", 5)).toBe(260);
    expect(zoomSize("list", 5)).toBe(136);
  });
  it("clamps zoom below 1 and above 5", () => {
    expect(zoomSize("grid", 0)).toBe(100);
    expect(zoomSize("list", 9)).toBe(136);
  });
  it("rounds fractional zoom", () => {
    expect(zoomSize("grid", 2.6)).toBe(160);
    expect(zoomSize("list", 2.6)).toBe(80);
  });
});

describe("columnCount", () => {
  it("computes columns for exact fit", () => {
    expect(columnCount(1000, 200, 0)).toBe(5);
  });
  it("returns at least 1 for tiny width", () => {
    expect(columnCount(10, 200, 0)).toBe(1);
  });
});

describe("dealMasonry", () => {
  it("keeps every index once, ascending per column", () => {
    const result = dealMasonry([1, 1, 1, 1, 1], 3);
    expect(result.flat().sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4]);
    for (const col of result) {
      for (let i = 1; i < col.length; i++) {
        expect(col[i]).toBeGreaterThan(col[i - 1]);
      }
    }
  });
  it("routes item after tall item (aspect 0.5) to column 1", () => {
    expect(dealMasonry([0.5, 1, 1, 1], 2)[1]).toContain(1);
  });
  it("resolves ties to the lowest column", () => {
    expect(dealMasonry([1, 1, 1], 2)[0]).toContain(2);
  });
  it("treats invalid aspect (0, NaN) as 1", () => {
    expect(dealMasonry([0, NaN, 1], 1)).toEqual([[0, 1, 2]]);
  });
  it("treats columns 0 as 1", () => {
    expect(dealMasonry([1, 1], 0)).toEqual([[0, 1]]);
  });
});

describe("wallRows", () => {
  it("every row non-empty, last row not stretched", () => {
    const rows = wallRows([1, 1, 1, 1, 1], 1000, 200, 16);
    for (const row of rows) expect(row.length).toBeGreaterThanOrEqual(1);
    expect(rows[rows.length - 1].length).toBeLessThan(rows[0].length);
  });
  it("packs 5 unit-aspect items correctly", () => {
    expect(wallRows([1, 1, 1, 1, 1], 1000, 200, 16)).toEqual([[0, 1, 2, 3], [4]]);
  });
});

describe("fallbackAspect", () => {
  it("returns explicit w/h ratio", () => {
    expect(fallbackAspect(undefined, 400, 200)).toBe(2);
  });
  it("returns 16/9 for video", () => {
    expect(fallbackAspect("video")).toBeCloseTo(16 / 9);
  });
  it("returns 2/3 for images", () => {
    expect(fallbackAspect("images")).toBeCloseTo(2 / 3);
  });
  it("returns 1 for unknown kind", () => {
    expect(fallbackAspect("unknown")).toBe(1);
  });
  it("returns 1 when width is zero", () => {
    expect(fallbackAspect(undefined, 0, 200)).toBe(1);
  });
});
