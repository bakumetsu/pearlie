import { describe, it, expect } from "vitest";
import { railColumns, RAIL_IMAGE, RAIL_VIDEO } from "./columns";

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
