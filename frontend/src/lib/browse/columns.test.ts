import { describe, it, expect } from "vitest";
import { railColumns, gridColumns, pageColumns, RAIL_IMAGE, RAIL_VIDEO } from "./columns";

const img = (w: number) => railColumns(w, RAIL_IMAGE.base, RAIL_IMAGE.maxTile, 8, RAIL_IMAGE.minTile);
const vid = (w: number) => railColumns(w, RAIL_VIDEO.base, RAIL_VIDEO.maxTile, 8, RAIL_VIDEO.minTile);

describe("railColumns", () => {
  it("keeps the base count at the 1152 px reference", () => {
    expect(img(1152)).toBe(7);
    expect(vid(1152)).toBe(5);
  });

  it("adds columns on wider screens (design table)", () => {
    expect(img(1764)).toBe(8);
    expect(img(2368)).toBe(11);
    expect(vid(1764)).toBe(6);
    expect(vid(2368)).toBe(8);
  });

  it("never goes under the base on narrow widths", () => {
    expect(img(800)).toBe(7);
    expect(vid(800)).toBe(5);
  });

  it("keeps tiles between min and max once above base", () => {
    for (let w = 1200; w <= 3800; w += 50) {
      const n = img(w);
      const tile = (w + 8) / n - 8;
      expect(tile).toBeLessThanOrEqual(220.0001);
      if (n > 7) expect(tile).toBeGreaterThanOrEqual(156);
    }
  });

  it("falls back to base for a zero width", () => {
    expect(railColumns(0, 7, 220, 8)).toBe(7);
  });
});

describe("gridColumns", () => {
  const g = (w: number, cell = 160, gap = 16) => gridColumns(w, cell, gap);

  it("keeps the old floor rule up to the 1152 px reference", () => {
    expect(g(1152)).toBe(6);
    expect(g(1000)).toBe(5);
    expect(g(300)).toBe(1);
    expect(g(0)).toBe(1);
  });

  it("adds columns on wide screens, tile stays within cell to 1.4 x cell", () => {
    for (const w of [1300, 1764, 2368, 3000, 3840]) {
      const n = g(w);
      const tile = (w + 16) / n - 16;
      expect(tile).toBeGreaterThanOrEqual(160 - 0.001);
      expect(tile).toBeLessThanOrEqual(160 * 1.4 + 0.001);
    }
    expect(g(1764)).toBeGreaterThanOrEqual(6);
    expect(g(2368)).toBeGreaterThan(g(1764));
  });

  it("never drops as the width grows", () => {
    let prev = 0;
    for (let w = 1000; w <= 3840; w += 8) {
      const n = g(w);
      expect(n).toBeGreaterThanOrEqual(prev);
      prev = n;
    }
  });
});

describe("pageColumns", () => {
  it("clamps to 5..8", () => {
    expect(pageColumns(0, 8)).toBe(5);
    expect(pageColumns(500, 8)).toBe(5);
    expect(pageColumns(800, 8)).toBe(6);
    expect(pageColumns(1100, 8)).toBe(8);
    expect(pageColumns(2400, 8)).toBe(8);
  });
});
