import { describe, it, expect } from "vitest";
import { nextAutohide, AUTOHIDE_TOP } from "./autohide";

describe("nextAutohide", () => {
  const far = AUTOHIDE_TOP + 500;

  it("hides on a scroll down past the delta", () => {
    expect(nextAutohide(false, far, far + 40, false)).toEqual({ hidden: true, lastY: far + 40 });
  });

  it("shows on a scroll up past the delta", () => {
    expect(nextAutohide(true, far, far - 40, false)).toEqual({ hidden: false, lastY: far - 40 });
  });

  it("ignores a move under the delta and keeps the anchor", () => {
    expect(nextAutohide(false, far, far + 3, false)).toEqual({ hidden: false, lastY: far });
    expect(nextAutohide(true, far, far - 3, false)).toEqual({ hidden: true, lastY: far });
  });

  it("is always shown near the top", () => {
    expect(nextAutohide(true, far, 10, false)).toEqual({ hidden: false, lastY: 10 });
  });

  it("never hides while a menu or sheet is open", () => {
    expect(nextAutohide(false, far, far + 100, true).hidden).toBe(false);
  });
});
