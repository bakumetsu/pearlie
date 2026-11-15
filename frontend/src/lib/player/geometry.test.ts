import { describe, it, expect } from "vitest";
import {
  dockBarRect,
  dockVideoRect,
  rectFor,
  rectsEqual,
  toTransform,
  modeOnLeave,
  formatTime,
  type Rect,
  type Viewport,
} from "./geometry";

const VP: Viewport = { w: 1440, h: 900 };

// Hand-computed from constants:
// dockBar:  x=72, y=900-72=828, w=1440-72=1368, h=72
// dockVideo: x=72+9+3=84, y=900-72+9=837, w=96, h=54
const DOCK_BAR: Rect = { x: 72, y: 828, w: 1368, h: 72 };
const DOCK_VIDEO_RECT: Rect = { x: 84, y: 837, w: 96, h: 54 };

describe("dockBarRect", () => {
  it("returns the full-width bar below the viewport bottom minus rail", () => {
    expect(dockBarRect(VP)).toEqual(DOCK_BAR);
  });
});

describe("dockVideoRect", () => {
  it("returns the 96×54 box centred vertically in the bar", () => {
    expect(dockVideoRect(VP)).toEqual(DOCK_VIDEO_RECT);
  });
});

describe("rectFor", () => {
  it("hidden → null", () => {
    expect(rectFor("hidden", DOCK_BAR, VP)).toBeNull();
  });

  it("mini → dock video rect", () => {
    expect(rectFor("mini", null, VP)).toEqual(DOCK_VIDEO_RECT);
  });

  it("stage with a valid slot → that slot", () => {
    const slot: Rect = { x: 200, y: 100, w: 800, h: 450 };
    expect(rectFor("stage", slot, VP)).toBe(slot);
  });

  it("stage with null slot → falls back to dock video rect", () => {
    expect(rectFor("stage", null, VP)).toEqual(DOCK_VIDEO_RECT);
  });

  it("stage with zero-size slot → falls back to dock video rect", () => {
    const zero: Rect = { x: 10, y: 10, w: 0, h: 0 };
    expect(rectFor("stage", zero, VP)).toEqual(DOCK_VIDEO_RECT);
  });
});

describe("rectsEqual", () => {
  it("identical rects → true", () => {
    expect(rectsEqual(DOCK_VIDEO_RECT, DOCK_VIDEO_RECT)).toBe(true);
  });

  it("within 0.5 px tolerance → true", () => {
    const b: Rect = { x: 84.4, y: 837.3, w: 96.2, h: 54.1 };
    expect(rectsEqual(DOCK_VIDEO_RECT, b)).toBe(true);
  });

  it("outside tolerance on one field → false", () => {
    const b: Rect = { x: 84, y: 837, w: 96, h: 54.6 };
    expect(rectsEqual(DOCK_VIDEO_RECT, b)).toBe(false);
  });

  it("both null → true", () => {
    expect(rectsEqual(null, null)).toBe(true);
  });

  it("one null, one rect → false", () => {
    expect(rectsEqual(null, DOCK_VIDEO_RECT)).toBe(false);
    expect(rectsEqual(DOCK_VIDEO_RECT, null)).toBe(false);
  });
});

describe("toTransform", () => {
  it("rounds to 2 decimal places", () => {
    expect(toTransform({ x: 1.234, y: 5.678, w: 10, h: 10 })).toBe(
      "translate(1.23px, 5.68px)",
    );
  });

  it("integer values have no trailing digits", () => {
    expect(toTransform({ x: 84, y: 837, w: 96, h: 54 })).toBe(
      "translate(84px, 837px)",
    );
  });
});

describe("modeOnLeave", () => {
  it("not ended → mini", () => {
    expect(modeOnLeave(false)).toBe("mini");
  });

  it("ended → hidden", () => {
    expect(modeOnLeave(true)).toBe("hidden");
  });
});

describe("formatTime", () => {
  it("0 → 0:00", () => {
    expect(formatTime(0)).toBe("0:00");
  });

  it("59 → 0:59", () => {
    expect(formatTime(59)).toBe("0:59");
  });

  it("61 → 1:01", () => {
    expect(formatTime(61)).toBe("1:01");
  });

  it("3600 → 1:00:00", () => {
    expect(formatTime(3600)).toBe("1:00:00");
  });

  it("NaN → 0:00", () => {
    expect(formatTime(NaN)).toBe("0:00");
  });

  it("-5 → 0:00", () => {
    expect(formatTime(-5)).toBe("0:00");
  });
});

describe("hidden rail", () => {
  it("dock bar starts at the left edge when railW is 0", () => {
    expect(dockBarRect(VP, 0)).toEqual({ ...DOCK_BAR, x: 0, w: VP.w });
  });

  it("dock video and rectFor follow railW", () => {
    const shifted = { ...DOCK_VIDEO_RECT, x: DOCK_VIDEO_RECT.x - 72 };
    expect(dockVideoRect(VP, 0)).toEqual(shifted);
    expect(rectFor("mini", null, VP, 0)).toEqual(shifted);
    expect(rectFor("stage", null, VP, 0)).toEqual(shifted);
  });
});
