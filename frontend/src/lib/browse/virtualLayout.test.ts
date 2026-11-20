import { describe, it, expect } from "vitest";
import { VirtualLayout, WALL_GAP, type Placed } from "./virtualLayout";
import { columnCount, dealMasonry, wallRows } from "./layout";
import { captionLines } from "./sources";
import { mockItems, randomAspects, rng } from "./testFixtures";
import type { Mode } from "./layout";

const W = 1000;

function snapshot(layout: VirtualLayout): Placed[] {
  return layout.range(-1, layout.total + 1);
}

function chunked(mode: Mode, size: number, aspects: number[], page: number, lines?: number[]): VirtualLayout {
  const layout = new VirtualLayout();
  layout.reset(mode, W, size, aspects.slice(0, page), { lines: lines?.slice(0, page) });
  for (let i = page; i < aspects.length; i += page) {
    layout.append(aspects.slice(i, i + page), { lines: lines?.slice(i, i + page) });
  }
  return layout;
}

function expectSame(a: Placed[], b: Placed[]): void {
  expect(a.length).toBe(b.length);
  for (let i = 0; i < a.length; i++) {
    expect(a[i].index).toBe(b[i].index);
    expect(a[i].rect.x).toBeCloseTo(b[i].rect.x, 6);
    expect(a[i].rect.y).toBeCloseTo(b[i].rect.y, 6);
    expect(a[i].rect.w).toBeCloseTo(b[i].rect.w, 6);
    expect(a[i].rect.h).toBeCloseTo(b[i].rect.h, 6);
  }
}

describe("test 1: chunked append equals one reset (5,000 items)", () => {
  const aspects = randomAspects(5000, 11);
  for (const mode of ["wall", "masonry", "grid", "list"] as Mode[]) {
    it(mode, () => {
      const lines = aspects.map((_a, i) => (i % 5 === 0 ? 2 : 1));
      const size = mode === "list" ? 64 : 120;
      const whole = new VirtualLayout();
      whole.reset(mode, W, size, aspects, { lines });
      const parts = chunked(mode, size, aspects, 50, lines);
      expect(parts.count).toBe(5000);
      expect(parts.total).toBeCloseTo(whole.total, 6);
      expectSame(snapshot(parts), snapshot(whole));
    });
  }

  it("masonry columns equal dealMasonry", () => {
    const layout = new VirtualLayout();
    layout.reset("masonry", W, 120, aspects);
    const dealt = dealMasonry(aspects, columnCount(W, 120, 8));
    const cw = (W - 8 * (dealt.length - 1)) / dealt.length;
    const placed = snapshot(layout);
    dealt.forEach((col, c) => {
      for (const i of col) expect(placed[i].rect.x).toBeCloseTo(c * (cw + 8), 6);
    });
  });
});

describe("test 2: range matches a linear scan", () => {
  const aspects = randomAspects(2000, 5);
  for (const mode of ["wall", "masonry", "grid", "list"] as Mode[]) {
    it(mode, () => {
      const lines = aspects.map((_a, i) => i % 3);
      const layout = new VirtualLayout();
      layout.reset(mode, W, mode === "list" ? 64 : 100, aspects, { lines });
      const all = snapshot(layout);
      expect(all.length).toBe(2000);
      const r = rng(99);
      for (let n = 0; n < 40; n++) {
        const top = r() * layout.total;
        const bottom = top + r() * 1500;
        const expected = all.filter((p) => p.rect.y + p.rect.h >= top && p.rect.y <= bottom).map((p) => p.index);
        expect(layout.range(top, bottom).map((p) => p.index)).toEqual(expected);
      }
    });
  }
});

describe("test 3: append time stays flat", () => {
  const sizes = [100, 1000, 5000, 20000];
  for (const mode of ["wall", "masonry", "grid", "list"] as Mode[]) {
    it(mode + " touches at most 70 items per 50-item append", () => {
      const times: number[] = [];
      for (const n of sizes) {
        const layout = new VirtualLayout();
        layout.reset(mode, W, mode === "list" ? 64 : 100, randomAspects(n, 3));
        const extra = randomAspects(50, 4);
        const t0 = performance.now();
        layout.append(extra);
        times.push(performance.now() - t0);
        expect(layout.stats.touched).toBeLessThanOrEqual(50 + 20);
        expect(layout.count).toBe(n + 50);
      }
      // Loose timing check (count above is the real assertion): 20,000 is not 5x slower than 100.
      expect(times[3]).toBeLessThan(Math.max(times[0] * 5, 5));
    });
  }
});

describe("test 4: aspect fix-up", () => {
  it("wall changes only rects from the item's row on", () => {
    const aspects = randomAspects(300, 8);
    const layout = new VirtualLayout();
    layout.reset("wall", W, 100, aspects);
    const before = snapshot(layout);
    const k = 150;
    const rowStart = before.findIndex((p) => p.rect.y === before[k].rect.y);
    layout.applyAspect(k, aspects[k] * 2);
    const after = snapshot(layout);
    expect(after.length).toBe(before.length);
    for (let i = 0; i < rowStart; i++) expect(after[i].rect).toEqual(before[i].rect);
    expect(after[k].rect.w).not.toBeCloseTo(before[k].rect.w, 3);
    // Same as a fresh build with the new aspect.
    const fresh = new VirtualLayout();
    fresh.reset("wall", W, 100, aspects.map((a, i) => (i === k ? a * 2 : a)));
    expectSame(after, snapshot(fresh));
  });

  it("masonry keeps the column and shifts only later tiles of that column", () => {
    const aspects = randomAspects(300, 9);
    const layout = new VirtualLayout();
    layout.reset("masonry", W, 100, aspects);
    const before = snapshot(layout);
    const k = 120;
    layout.applyAspect(k, aspects[k] * 3);
    const after = snapshot(layout);
    const col = before[k].rect.x;
    for (let i = 0; i < before.length; i++) {
      expect(after[i].rect.x).toBe(before[i].rect.x);
      if (before[i].rect.x !== col || i < k) expect(after[i].rect.y).toBe(before[i].rect.y);
    }
    expect(after[k].rect.h).toBeCloseTo(before[k].rect.h / 3, 6);
    const later = before.findIndex((p, i) => i > k && p.rect.x === col);
    expect(after[later].rect.y).not.toBeCloseTo(before[later].rect.y, 3);
  });

  it("grid redoes the row and moves later rows", () => {
    const aspects = randomAspects(100, 2);
    const layout = new VirtualLayout();
    layout.reset("grid", W, 100, aspects);
    const before = snapshot(layout);
    layout.applyAspect(0, 0.1);
    const after = snapshot(layout);
    expect(after[0].rect.h).toBeGreaterThan(before[0].rect.h);
    expect(after[after.length - 1].rect.y).toBeGreaterThan(before[before.length - 1].rect.y);
  });
});

describe("test 13 (layout): grid and list rows use the tallest caption", () => {
  const cols = columnCount(W, 100, 16);
  it("grid: a 2-line tile lifts its row only", () => {
    const n = cols * 3;
    const aspects = new Array(n).fill(1);
    const lines = new Array(n).fill(1);
    lines[1] = 2;
    const layout = new VirtualLayout({ lineH: 20, pad: 6 });
    layout.reset("grid", W, 100, aspects, { lines });
    const cw = (W - 16 * (cols - 1)) / cols;
    const rects = snapshot(layout);
    expect(rects[0].rect.h).toBeCloseTo(cw + 2 * 20 + 6, 6);
    expect(rects[cols].rect.h).toBeCloseTo(cw + 1 * 20 + 6, 6);
    expect(rects[cols].rect.y).toBeCloseTo(cw + 46 + 16, 6);
  });

  it("list: a 2-line row is taller than a 1-line row", () => {
    const layout = new VirtualLayout({ lineH: 20, listPad: 16 });
    layout.reset("list", W, 20, [1, 1, 1], { lines: [1, 2, 1] });
    const r = snapshot(layout).map((p) => p.rect.h);
    expect(r[0]).toBe(56 + 1);
    expect(r[1]).toBe(Math.max(20, 40) + 16 + 1);
    expect(r[2]).toBe(r[0]);
    expect(layout.total).toBe(r[0] + r[1] + r[2]);
  });

  it("list: row height holds the thumb plus the tile padding, with no gap or overlap", () => {
    const layout = new VirtualLayout({ lineH: 20, listPad: 16 });
    layout.reset("list", W, 120, [1, 1], { lines: [1, 2] });
    const p = snapshot(layout);
    expect(p[0].rect.h).toBe(120 + 16 + 1);
    expect(p[1].rect.h).toBe(120 + 16 + 1);
    expect(p[1].rect.y).toBe(p[0].rect.y + p[0].rect.h);
  });

  it("captionLines follows the tile rules", () => {
    const items = mockItems(400, 4);
    for (const item of items) {
      const lines = captionLines(item, "list");
      expect(lines === 1 || lines === 2).toBe(true);
      if ("post_id" in item) {
        expect(captionLines(item, "grid")).toBe(0);
        expect(lines).toBe(item.title ? 2 : 1);
      }
    }
    expect(captionLines({ kind: "image", id: "1", title: "t", thumb_url: "", favorite: false, added_at: "" } as never, "grid")).toBe(0);
    expect(captionLines({ kind: "video", id: "1", title: "t", thumb_url: "", favorite: false, added_at: "" } as never, "grid")).toBe(1);
  });
});

describe("test 14: wall equals wallRows and the flex result", () => {
  const aspects = randomAspects(1500, 21);
  for (const size of [100, 180, 320]) {
    it("rows and cell widths at size " + size, () => {
      const layout = new VirtualLayout();
      layout.reset("wall", W, size, aspects);
      const placed = snapshot(layout);
      const rows = wallRows(aspects, W, size, WALL_GAP);
      let top = 0;
      rows.forEach((row, r) => {
        const last = r === rows.length - 1;
        const sum = row.reduce((s, i) => s + aspects[i], 0);
        const gaps = WALL_GAP * (row.length - 1);
        // Flex `aspect 1 0%`: closed rows share the width by aspect; the open row keeps the natural size.
        const h = last && sum * size + gaps <= W ? size : (W - gaps) / sum;
        row.forEach((i) => {
          expect(placed[i].rect.y).toBeCloseTo(top, 6);
          expect(placed[i].rect.h).toBeCloseTo(h, 6);
          expect(placed[i].rect.w).toBeCloseTo(aspects[i] * h, 6);
        });
        const lastCell = placed[row[row.length - 1]].rect;
        if (!last) expect(lastCell.x + lastCell.w).toBeCloseTo(W, 6);
        top += h + WALL_GAP;
      });
      expect(layout.total).toBeCloseTo(top - WALL_GAP, 6);
    });
  }
});

describe("key map", () => {
  it("maps keys to indexes across reset and append", () => {
    const layout = new VirtualLayout();
    layout.reset("grid", W, 100, [1, 1], { keys: ["a", "b"] });
    layout.append([1], { keys: ["c"] });
    expect(layout.indexOf("c")).toBe(2);
    expect(layout.keyAt(1)).toBe("b");
    expect(layout.indexOf("zz")).toBe(-1);
  });
});

describe("wide grid (D-41 3.3)", () => {
  it("adds columns past the reference width (tiles grow up to 1.4 x) and keeps the tile within cell to 1.4 x cell", () => {
    const layout = new VirtualLayout();
    const width = 2368;
    layout.reset("grid", width, 160, randomAspects(200, 5));
    const rects = snapshot(layout);
    const xs = new Set(rects.map((p) => Math.round(p.rect.x)));
    const tile = rects[0].rect.w;
    expect(xs.size).toBe(10);
    expect(xs.size).toBeGreaterThan(columnCount(1152, 160, 16));
    expect(tile).toBeGreaterThanOrEqual(160 - 0.001);
    expect(tile).toBeLessThanOrEqual(160 * 1.4 + 0.001);
  });
});
