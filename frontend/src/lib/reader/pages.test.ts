import { describe, it, expect } from "vitest";
import {
  clampPage,
  bookStart,
  isCompleted,
  pageSrc,
  defaultMode,
  buildGroups,
  groupOf,
  displayOrder,
  stepGroup,
  preloadPages,
  zoneAction,
  fitScale,
  zoomStep,
  ZOOM_STEPS,
  segmentLayout,
  pageFromRatio,
  shouldWheelTurn,
  WHEEL_MIN_DELTA,
  WHEEL_MIN_GAP_MS,
  keyAction,
} from "./pages";

describe("clampPage", () => {
  it("clamps below 1 to 1", () => {
    expect(clampPage(0, 10)).toBe(1);
    expect(clampPage(-5, 10)).toBe(1);
  });

  it("clamps above count to count", () => {
    expect(clampPage(15, 10)).toBe(10);
  });

  it("returns page unchanged when in range", () => {
    expect(clampPage(5, 10)).toBe(5);
    expect(clampPage(1, 10)).toBe(1);
    expect(clampPage(10, 10)).toBe(10);
  });

  it("returns 1 for NaN", () => {
    expect(clampPage(NaN, 10)).toBe(1);
  });

  it("returns 1 when count is 0", () => {
    expect(clampPage(5, 0)).toBe(1);
  });
});

describe("defaultMode", () => {
  it("is single", () => {
    expect(defaultMode()).toBe("single");
  });
});

describe("buildGroups", () => {
  it("single mode produces one page per group", () => {
    expect(buildGroups(5, "single", new Set())).toEqual([[1], [2], [3], [4], [5]]);
  });

  it("spread mode: cover alone, then pairs", () => {
    expect(buildGroups(5, "spread", new Set())).toEqual([[1], [2, 3], [4, 5]]);
  });

  it("spread mode: wide page stands alone", () => {
    expect(buildGroups(5, "spread", new Set([2]))).toEqual([[1], [2], [3, 4], [5]]);
  });

  it("spread mode: last odd page alone", () => {
    expect(buildGroups(4, "spread", new Set())).toEqual([[1], [2, 3], [4]]);
  });

  it("count 0 returns empty array", () => {
    expect(buildGroups(0, "spread", new Set())).toEqual([]);
  });

  it("wide page 3 in count 6", () => {
    expect(buildGroups(6, "spread", new Set([3]))).toEqual([[1], [2], [3], [4, 5], [6]]);
  });

  it("scroll mode produces one page per group", () => {
    expect(buildGroups(3, "scroll", new Set())).toEqual([[1], [2], [3]]);
  });
});

describe("groupOf", () => {
  it("finds the group containing the page", () => {
    expect(groupOf([[1], [2, 3], [4, 5]], 3)).toEqual([2, 3]);
    expect(groupOf([[1], [2, 3], [4, 5]], 4)).toEqual([4, 5]);
    expect(groupOf([[1], [2, 3], [4, 5]], 1)).toEqual([1]);
  });

  it("returns empty array when no groups", () => {
    expect(groupOf([], 5)).toEqual([]);
  });

  it("clamps page below range to first group", () => {
    expect(groupOf([[1], [2, 3], [4, 5]], 0)).toEqual([1]);
  });

  it("clamps page above range to last group", () => {
    expect(groupOf([[1], [2, 3], [4, 5]], 100)).toEqual([4, 5]);
  });
});

describe("displayOrder", () => {
  it("returns same order for ltr", () => {
    expect(displayOrder([2, 3], "ltr")).toEqual([2, 3]);
  });

  it("reverses order for rtl", () => {
    expect(displayOrder([2, 3], "rtl")).toEqual([3, 2]);
  });

  it("single page group unchanged", () => {
    expect(displayOrder([1], "rtl")).toEqual([1]);
  });
});

describe("stepGroup", () => {
  const groups = [[1], [2, 3], [4, 5]];

  it("forward: returns first page of next group", () => {
    expect(stepGroup(groups, 1, 1)).toBe(2);
    expect(stepGroup(groups, 3, 1)).toBe(4);
  });

  it("backward: returns first page of previous group", () => {
    expect(stepGroup(groups, 3, -1)).toBe(1);
    expect(stepGroup(groups, 5, -1)).toBe(2);
  });

  it("forward from last group returns 'end'", () => {
    expect(stepGroup(groups, 5, 1)).toBe("end");
  });

  it("backward from first group returns null", () => {
    expect(stepGroup(groups, 1, -1)).toBeNull();
  });

  it("spread mode with wide page", () => {
    const spreadGroups = [[1], [2], [3, 4], [5]];
    expect(stepGroup(spreadGroups, 1, 1)).toBe(2);
    expect(stepGroup(spreadGroups, 2, 1)).toBe(3);
    expect(stepGroup(spreadGroups, 4, -1)).toBe(2);
  });

  it("empty groups forward returns 'end'", () => {
    expect(stepGroup([], 1, 1)).toBe("end");
  });

  it("empty groups backward returns null", () => {
    expect(stepGroup([], 1, -1)).toBeNull();
  });
});

describe("preloadPages", () => {
  const groups = [[1], [2, 3], [4, 5], [6, 7]];

  it("preloads first page of next two groups", () => {
    expect(preloadPages(groups, 1)).toEqual([2, 4]);
  });

  it("returns fewer pages near the end", () => {
    expect(preloadPages(groups, 5)).toEqual([6]);
    expect(preloadPages(groups, 7)).toEqual([]);
  });

  it("returns empty for empty groups", () => {
    expect(preloadPages([], 1)).toEqual([]);
  });
});

describe("zoneAction", () => {
  it("ltr: left third is prev", () => {
    expect(zoneAction(100, 1000, "ltr")).toBe("prev");
  });

  it("ltr: right third is next", () => {
    expect(zoneAction(900, 1000, "ltr")).toBe("next");
  });

  it("ltr: middle is toggle", () => {
    expect(zoneAction(500, 1000, "ltr")).toBe("toggle");
  });

  it("rtl: left third is next", () => {
    expect(zoneAction(100, 1000, "rtl")).toBe("next");
  });

  it("rtl: right third is prev", () => {
    expect(zoneAction(900, 1000, "rtl")).toBe("prev");
  });

  it("rtl: middle is toggle", () => {
    expect(zoneAction(500, 1000, "rtl")).toBe("toggle");
  });
});

describe("fitScale", () => {
  it("width fit", () => {
    expect(fitScale("width", 100, { w: 1000, h: 800 }, { w: 500, h: 700 }, 1)).toBe(2);
  });

  it("height fit", () => {
    expect(fitScale("height", 100, { w: 1000, h: 800 }, { w: 500, h: 700 }, 1)).toBeCloseTo(80 / 70);
  });

  it("both fit takes the minimum", () => {
    // width part: 1000/500 = 2, height part: 800/700 ≈ 1.143
    expect(fitScale("both", 100, { w: 1000, h: 800 }, { w: 500, h: 700 }, 1)).toBeCloseTo(80 / 70);
  });

  it("actual fit returns 1 * zoom", () => {
    expect(fitScale("actual", 100, { w: 1000, h: 800 }, { w: 500, h: 700 }, 1)).toBe(1);
    expect(fitScale("actual", 150, { w: 1000, h: 800 }, { w: 500, h: 700 }, 1)).toBe(1.5);
  });

  it("zoom 200 doubles the scale", () => {
    expect(fitScale("width", 200, { w: 1000, h: 800 }, { w: 500, h: 700 }, 1)).toBe(4);
  });

  it("pagesAcross 2 halves width scale", () => {
    expect(fitScale("width", 100, { w: 1000, h: 800 }, { w: 500, h: 700 }, 2)).toBe(1);
  });

  it("zero view size returns 1", () => {
    expect(fitScale("width", 100, { w: 0, h: 800 }, { w: 500, h: 700 }, 1)).toBe(1);
  });

  it("zero page size returns 1", () => {
    expect(fitScale("width", 100, { w: 1000, h: 800 }, { w: 0, h: 700 }, 1)).toBe(1);
  });
});

describe("zoomStep", () => {
  it("steps up from 100 to 150", () => {
    expect(zoomStep(100, 1)).toBe(150);
  });

  it("steps down from 150 to 100", () => {
    expect(zoomStep(150, -1)).toBe(100);
  });

  it("clamped at max (300)", () => {
    expect(zoomStep(300, 1)).toBe(300);
  });

  it("clamped at min (50)", () => {
    expect(zoomStep(50, -1)).toBe(50);
  });

  it("between steps: 80 up goes to 100", () => {
    expect(zoomStep(80, 1)).toBe(100);
  });

  it("between steps: 80 down goes to 75", () => {
    expect(zoomStep(80, -1)).toBe(75);
  });

  it("between steps: 125 up goes to 150", () => {
    expect(zoomStep(125, 1)).toBe(150);
  });

  it("between steps: 125 down goes to 100", () => {
    expect(zoomStep(125, -1)).toBe(100);
  });

  it("all steps are valid", () => {
    for (const s of ZOOM_STEPS) {
      const next = zoomStep(s, 1);
      expect(next).toBeGreaterThanOrEqual(50);
      expect(next).toBeLessThanOrEqual(300);
      const prev = zoomStep(s, -1);
      expect(prev).toBeGreaterThanOrEqual(50);
      expect(prev).toBeLessThanOrEqual(300);
    }
  });
});

describe("segmentLayout", () => {
  it("150 pages at 800px uses segments", () => {
    expect(segmentLayout(150, 800)).toEqual({ kind: "segments", count: 150 });
  });

  it("250 pages uses track (exceeds 200)", () => {
    expect(segmentLayout(250, 800)).toEqual({ kind: "track" });
  });

  it("100 pages at 300px uses track (px per segment < 4)", () => {
    expect(segmentLayout(100, 300)).toEqual({ kind: "track" });
  });

  it("boundary: exactly 200 pages with sufficient width uses segments", () => {
    expect(segmentLayout(200, 800)).toEqual({ kind: "segments", count: 200 });
  });

  it("boundary: exactly 4px per segment uses segments", () => {
    expect(segmentLayout(100, 400)).toEqual({ kind: "segments", count: 100 });
  });
});

describe("pageFromRatio", () => {
  it("ltr: ratio 0 gives page 1", () => {
    expect(pageFromRatio(0, 10, "ltr")).toBe(1);
  });

  it("ltr: ratio 1 gives page 10", () => {
    expect(pageFromRatio(1, 10, "ltr")).toBe(10);
  });

  it("ltr: ratio 0.45 gives the middle page", () => {
    expect(pageFromRatio(0.45, 10, "ltr")).toBe(5);
  });

  it("rtl: ratio 0 gives last page", () => {
    expect(pageFromRatio(0, 10, "rtl")).toBe(10);
  });

  it("rtl: ratio 1 gives first page", () => {
    expect(pageFromRatio(1, 10, "rtl")).toBe(1);
  });

  it("clamps ratio below 0", () => {
    expect(pageFromRatio(-1, 10, "ltr")).toBe(1);
  });

  it("clamps ratio above 1", () => {
    expect(pageFromRatio(2, 10, "ltr")).toBe(10);
  });

  it("count 0 returns 1", () => {
    expect(pageFromRatio(0.5, 0, "ltr")).toBe(1);
  });
});

describe("shouldWheelTurn", () => {
  it("delta 39 is below threshold", () => {
    expect(shouldWheelTurn(39, 1000, 0)).toBe(false);
  });

  it("delta 40 meets threshold", () => {
    expect(shouldWheelTurn(40, 1000, 0)).toBe(true);
  });

  it("second turn within 349 ms is rejected", () => {
    expect(shouldWheelTurn(40, 349, 0)).toBe(false);
  });

  it("turn at exactly 350 ms is accepted", () => {
    expect(shouldWheelTurn(40, 350, 0)).toBe(true);
  });

  it("negative delta with sufficient magnitude", () => {
    expect(shouldWheelTurn(-40, 1000, 0)).toBe(true);
    expect(shouldWheelTurn(-39, 1000, 0)).toBe(false);
  });

  it("exports constants", () => {
    expect(WHEEL_MIN_DELTA).toBe(40);
    expect(WHEEL_MIN_GAP_MS).toBe(350);
  });
});

describe("keyAction", () => {
  it("ArrowRight ltr -> next", () => {
    expect(keyAction({ key: "ArrowRight" }, "ltr")).toBe("next");
  });

  it("ArrowRight rtl -> prev", () => {
    expect(keyAction({ key: "ArrowRight" }, "rtl")).toBe("prev");
  });

  it("ArrowLeft ltr -> prev", () => {
    expect(keyAction({ key: "ArrowLeft" }, "ltr")).toBe("prev");
  });

  it("ArrowLeft rtl -> next", () => {
    expect(keyAction({ key: "ArrowLeft" }, "rtl")).toBe("next");
  });

  it("space (no shift) -> next", () => {
    expect(keyAction({ key: " " }, "ltr")).toBe("next");
  });

  it("Shift+space -> prev", () => {
    expect(keyAction({ key: " ", shiftKey: true }, "ltr")).toBe("prev");
  });

  it("PageDown -> next", () => {
    expect(keyAction({ key: "PageDown" }, "ltr")).toBe("next");
  });

  it("PageUp -> prev", () => {
    expect(keyAction({ key: "PageUp" }, "ltr")).toBe("prev");
  });

  it("Home -> first", () => {
    expect(keyAction({ key: "Home" }, "ltr")).toBe("first");
  });

  it("End -> last", () => {
    expect(keyAction({ key: "End" }, "ltr")).toBe("last");
  });

  it("'[' -> book-prev", () => {
    expect(keyAction({ key: "[" }, "ltr")).toBe("book-prev");
  });

  it("']' -> book-next", () => {
    expect(keyAction({ key: "]" }, "ltr")).toBe("book-next");
  });

  it("'b' -> books", () => {
    expect(keyAction({ key: "b" }, "ltr")).toBe("books");
  });

  it("'s' -> settings", () => {
    expect(keyAction({ key: "s" }, "ltr")).toBe("settings");
  });

  it("'f' -> fit", () => {
    expect(keyAction({ key: "f" }, "ltr")).toBe("fit");
  });

  it("'F' -> fullscreen", () => {
    expect(keyAction({ key: "F" }, "ltr")).toBe("fullscreen");
  });

  it("'m' -> mode", () => {
    expect(keyAction({ key: "m" }, "ltr")).toBe("mode");
  });

  it("'1' -> mode-single", () => {
    expect(keyAction({ key: "1" }, "ltr")).toBe("mode-single");
  });

  it("'2' -> mode-spread", () => {
    expect(keyAction({ key: "2" }, "ltr")).toBe("mode-spread");
  });

  it("'3' -> mode-scroll", () => {
    expect(keyAction({ key: "3" }, "ltr")).toBe("mode-scroll");
  });

  it("'?' -> help", () => {
    expect(keyAction({ key: "?" }, "ltr")).toBe("help");
  });

  it("'t' -> thumbs", () => {
    expect(keyAction({ key: "t" }, "ltr")).toBe("thumbs");
  });

  it("'-\" -> zoom-out", () => {
    expect(keyAction({ key: "-" }, "ltr")).toBe("zoom-out");
  });

  it("'+' -> zoom-in", () => {
    expect(keyAction({ key: "+" }, "ltr")).toBe("zoom-in");
  });

  it("'=' -> zoom-in", () => {
    expect(keyAction({ key: "=" }, "ltr")).toBe("zoom-in");
  });

  it("'0' -> zoom-reset", () => {
    expect(keyAction({ key: "0" }, "ltr")).toBe("zoom-reset");
  });

  it("'h' -> hide", () => {
    expect(keyAction({ key: "h" }, "ltr")).toBe("hide");
  });

  it("'r' -> dir", () => {
    expect(keyAction({ key: "r" }, "ltr")).toBe("dir");
  });

  it("Escape -> escape", () => {
    expect(keyAction({ key: "Escape" }, "ltr")).toBe("escape");
  });

  it("ArrowUp -> scroll-up", () => {
    expect(keyAction({ key: "ArrowUp" }, "ltr")).toBe("scroll-up");
  });

  it("ArrowDown -> scroll-down", () => {
    expect(keyAction({ key: "ArrowDown" }, "ltr")).toBe("scroll-down");
  });

  it("Ctrl modifier returns null", () => {
    expect(keyAction({ key: "ArrowRight", ctrlKey: true }, "ltr")).toBeNull();
  });

  it("Meta modifier returns null", () => {
    expect(keyAction({ key: "f", metaKey: true }, "ltr")).toBeNull();
  });

  it("Alt modifier returns null", () => {
    expect(keyAction({ key: "b", altKey: true }, "ltr")).toBeNull();
  });

  it("unknown key returns null", () => {
    expect(keyAction({ key: "x" }, "ltr")).toBeNull();
    expect(keyAction({ key: "z" }, "rtl")).toBeNull();
  });
});

describe("isCompleted", () => {
  it("true when page equals count", () => {
    expect(isCompleted(5, 5)).toBe(true);
  });

  it("true when page exceeds count", () => {
    expect(isCompleted(6, 5)).toBe(true);
  });

  it("false when page is less than count", () => {
    expect(isCompleted(4, 5)).toBe(false);
  });

  it("false when count is 0", () => {
    expect(isCompleted(1, 0)).toBe(false);
  });
});

describe("pageSrc", () => {
  it("replaces {n} with the page number", () => {
    expect(pageSrc("/api/pages/{n}", 3)).toBe("/api/pages/3");
  });

  it("replaces {n} in a filename template", () => {
    expect(pageSrc("page_{n}.jpg", 12)).toBe("page_12.jpg");
  });

  it("no {n} placeholder returns template unchanged", () => {
    expect(pageSrc("/static/image.png", 1)).toBe("/static/image.png");
  });
});

describe("bookStart", () => {
  it("unread null returns 1", () => {
    expect(bookStart({ read_page: null, page_count: 20 })).toBe(1);
  });

  it("read_page 0 returns 1", () => {
    expect(bookStart({ read_page: 0, page_count: 20 })).toBe(1);
  });

  it("in progress returns read_page", () => {
    expect(bookStart({ read_page: 5, page_count: 20 })).toBe(5);
  });

  it("completed returns 1", () => {
    expect(bookStart({ read_page: 20, page_count: 20 })).toBe(1);
  });

  it("missing page_count returns 1", () => {
    expect(bookStart({ read_page: 5 })).toBe(1);
  });
});
