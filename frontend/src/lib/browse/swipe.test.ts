// swipe tests (T-67)
import { describe, it, expect } from "vitest";
import { swipeDir } from "./swipe";

describe("swipeDir", () => {
  it("returns null at exactly the minimum horizontal distance", () => {
    expect(swipeDir(-60, 0)).toBeNull();
    expect(swipeDir(60, 0)).toBeNull();
  });

  it("returns a direction just beyond the minimum horizontal distance", () => {
    expect(swipeDir(-61, 0)).toBe(1);
    expect(swipeDir(61, 0)).toBe(-1);
  });

  it("returns null when |dx| equals 1.5 * |dy|", () => {
    expect(swipeDir(-90, 60)).toBeNull();
    expect(swipeDir(90, -60)).toBeNull();
  });

  it("returns null for vertical motion", () => {
    expect(swipeDir(0, 200)).toBeNull();
  });

  it("maps left to next and right to previous", () => {
    expect(swipeDir(-100, 10)).toBe(1);
    expect(swipeDir(100, -10)).toBe(-1);
  });
});
