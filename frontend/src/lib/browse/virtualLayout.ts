import type { Mode } from "./layout";
import { columnCount, safeAspect } from "./layout";

// Pure, incremental layout for the windowed results grid (D-31). No DOM: it holds a rect per item
// index and the total height. All modes share reset / append / applyAspect / range.

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Placed {
  index: number;
  rect: Rect;
}

export interface LayoutOptions {
  // Caption line height and padding; defaults until the grid measures them.
  lineH: number;
  pad: number;
  listPad: number;
}

export interface LayoutExtra {
  // Caption lines per item (grid and list rows) and keys for the key-to-index map.
  lines?: number[];
  keys?: string[];
}

export const WALL_GAP = 2;
export const MASONRY_GAP = 8;
export const GRID_GAP = 16;

const DEFAULTS: LayoutOptions = { lineH: 18, pad: 8, listPad: 16 };

interface Row {
  start: number;
  end: number; // exclusive
  top: number;
  h: number;
}

export class VirtualLayout {
  mode: Mode = "grid";
  width = 0;
  size = 100;
  opts: LayoutOptions;
  // Items processed by the last call (tests use it to prove flat append time).
  stats = { touched: 0 };

  private aspects: number[] = [];
  private lines: number[] = [];
  private keys: string[] = [];
  private keyIndex = new Map<string, number>();

  // wall, grid and list: rows. Grid and list also use `cols` and `cw`.
  private rows: Row[] = [];
  private rowMaxH: number[] = [];
  private cols = 1;
  private cw = 0;

  // masonry: per column the item indices; per item its column and top. Choice heights ignore gaps
  // (the same rule as dealMasonry, so the column choice does not drift).
  private colItems: number[][] = [];
  private colDealH: number[] = [];
  private colBottom: number[] = [];
  private itemCol: number[] = [];
  private itemTop: number[] = [];

  constructor(opts: Partial<LayoutOptions> = {}) {
    this.opts = { ...DEFAULTS, ...opts };
  }

  get count(): number {
    return this.aspects.length;
  }

  get total(): number {
    if (this.mode === "masonry") {
      let t = 0;
      for (let c = 0; c < this.cols; c++) {
        if (this.colItems[c].length > 0) t = Math.max(t, this.colBottom[c]);
      }
      return t;
    }
    const last = this.rows[this.rows.length - 1];
    return last ? last.top + last.h : 0;
  }

  keyAt(index: number): string | undefined {
    return this.keys[index];
  }

  indexOf(key: string): number {
    return this.keyIndex.get(key) ?? -1;
  }

  setOptions(opts: Partial<LayoutOptions>): void {
    this.opts = { ...this.opts, ...opts };
  }

  reset(mode: Mode, width: number, size: number, aspects: number[], extra: LayoutExtra = {}): void {
    this.mode = mode;
    this.width = width;
    this.size = size;
    this.aspects = aspects.map(safeAspect);
    this.lines = aspects.map((_a, i) => extra.lines?.[i] ?? 0);
    this.keys = extra.keys ? extra.keys.slice(0, aspects.length) : [];
    this.keyIndex = new Map();
    this.keys.forEach((k, i) => this.keyIndex.set(k, i));
    this.rows = [];
    this.rowMaxH = [];
    this.colItems = [];
    this.colDealH = [];
    this.colBottom = [];
    this.itemCol = [];
    this.itemTop = [];
    if (mode === "masonry") {
      this.cols = columnCount(width, size, MASONRY_GAP);
      this.cw = (width - MASONRY_GAP * (this.cols - 1)) / this.cols;
      for (let c = 0; c < this.cols; c++) {
        this.colItems.push([]);
        this.colDealH.push(0);
        this.colBottom.push(0);
      }
    } else if (mode === "grid") {
      this.cols = columnCount(width, size, GRID_GAP);
      this.cw = (width - GRID_GAP * (this.cols - 1)) / this.cols;
    } else if (mode === "list") {
      this.cols = 1;
      this.cw = width;
    }
    this.stats.touched = 0;
    this.build(0);
  }

  append(aspects: number[], extra: LayoutExtra = {}): void {
    const from = this.aspects.length;
    for (let i = 0; i < aspects.length; i++) {
      this.aspects.push(safeAspect(aspects[i]));
      this.lines.push(extra.lines?.[i] ?? 0);
      const key = extra.keys?.[i];
      if (key !== undefined) {
        this.keys[from + i] = key;
        this.keyIndex.set(key, from + i);
      }
    }
    this.stats.touched = 0;
    this.build(from);
  }

  // Fix-up for a picture whose real shape differs from the estimate. Wall reflows from the item's
  // row; masonry keeps the column and shifts later tiles of that column; grid and list redo the row.
  applyAspect(index: number, aspect: number): void {
    if (index < 0 || index >= this.aspects.length) return;
    const old = this.aspects[index];
    this.aspects[index] = safeAspect(aspect);
    this.stats.touched = 0;
    if (this.mode === "masonry") {
      const c = this.itemCol[index];
      const items = this.colItems[c];
      let p = this.lowerBound(items, index);
      this.colDealH[c] += 1 / this.aspects[index] - 1 / old;
      let bottom = p > 0 ? this.itemTop[items[p - 1]] + this.itemH(items[p - 1]) + MASONRY_GAP : 0;
      for (; p < items.length; p++) {
        this.itemTop[items[p]] = bottom;
        bottom += this.itemH(items[p]) + MASONRY_GAP;
        this.stats.touched++;
      }
      this.colBottom[c] = bottom - MASONRY_GAP;
      return;
    }
    const r = this.rowOf(index);
    if (this.mode === "wall") {
      const start = this.rows[r].start;
      this.rows.length = r;
      this.rowMaxH.length = r;
      this.buildWallRows(start);
      return;
    }
    const row = this.rows[r];
    this.rowMaxH[r] = this.scanRowMax(row.start, row.end);
    this.stats.touched += row.end - row.start;
    this.settleFrom(r);
  }

  // Items that intersect [top, bottom], in index order.
  range(top: number, bottom: number): Placed[] {
    const out: Placed[] = [];
    if (this.aspects.length === 0) return out;
    if (this.mode === "masonry") {
      for (let c = 0; c < this.cols; c++) {
        const items = this.colItems[c];
        let lo = 0;
        let hi = items.length;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (this.itemTop[items[mid]] + this.itemH(items[mid]) < top) lo = mid + 1;
          else hi = mid;
        }
        for (let p = lo; p < items.length; p++) {
          const i = items[p];
          if (this.itemTop[i] > bottom) break;
          out.push({ index: i, rect: this.masonryRect(i) });
        }
      }
      return out.sort((a, b) => a.index - b.index);
    }
    let lo = 0;
    let hi = this.rows.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.rows[mid].top + this.rows[mid].h < top) lo = mid + 1;
      else hi = mid;
    }
    for (let r = lo; r < this.rows.length; r++) {
      if (this.rows[r].top > bottom) break;
      this.pushRowRects(r, out);
    }
    return out;
  }

  rect(index: number): Rect | undefined {
    if (index < 0 || index >= this.aspects.length) return undefined;
    if (this.mode === "masonry") return this.masonryRect(index);
    const out: Placed[] = [];
    this.pushRowRects(this.rowOf(index), out);
    return out.find((e) => e.index === index)?.rect;
  }

  // ---- internals ----

  private itemH(i: number): number {
    return this.cw / this.aspects[i];
  }

  private masonryRect(i: number): Rect {
    const c = this.itemCol[i];
    return { x: c * (this.cw + MASONRY_GAP), y: this.itemTop[i], w: this.cw, h: this.itemH(i) };
  }

  // Grid: picture plus caption. List: the larger of thumb and caption, plus the 1 px border.
  private cellH(i: number): number {
    const { lineH, pad, listPad } = this.opts;
    if (this.mode === "list") return Math.max(this.size, this.lines[i] * lineH + listPad) + 1;
    return this.cw / this.aspects[i] + (this.lines[i] > 0 ? this.lines[i] * lineH + pad : 0);
  }

  private scanRowMax(start: number, end: number): number {
    let m = 0;
    for (let i = start; i < end; i++) m = Math.max(m, this.cellH(i));
    return m;
  }

  private lowerBound(items: number[], index: number): number {
    let lo = 0;
    let hi = items.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (items[mid] < index) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  private rowOf(index: number): number {
    let lo = 0;
    let hi = this.rows.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.rows[mid].start <= index) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  private rowGap(): number {
    return this.mode === "wall" ? WALL_GAP : this.mode === "grid" ? GRID_GAP : 0;
  }

  private build(from: number): void {
    const n = this.aspects.length;
    if (this.mode === "masonry") {
      for (let i = from; i < n; i++) {
        let c = 0;
        for (let k = 1; k < this.cols; k++) {
          if (this.colDealH[k] < this.colDealH[c]) c = k;
        }
        const top = this.colItems[c].length ? this.colBottom[c] + MASONRY_GAP : 0;
        this.itemCol[i] = c;
        this.itemTop[i] = top;
        this.colBottom[c] = top + this.itemH(i);
        this.colDealH[c] += 1 / this.aspects[i];
        this.colItems[c].push(i);
        this.stats.touched++;
      }
      return;
    }
    if (this.mode === "wall") {
      // Re-open the last row; closed rows are never touched.
      let start = from;
      if (from > 0 && this.rows.length > 0) {
        start = this.rows.pop()!.start;
        this.rowMaxH.pop();
      }
      this.buildWallRows(start);
      return;
    }
    // grid and list: rows of `cols` items; only the last row grows.
    let r = this.rows.length - 1;
    for (let i = from; i < n; i++) {
      if (r < 0 || this.rows[r].end - this.rows[r].start >= this.cols) {
        const prev = this.rows[r];
        this.rows.push({ start: i, end: i, top: prev ? prev.top + prev.h + this.rowGap() : 0, h: 0 });
        this.rowMaxH.push(0);
        r++;
      }
      const row = this.rows[r];
      row.end = i + 1;
      this.rowMaxH[r] = Math.max(this.rowMaxH[r], this.cellH(i));
      row.h = this.rowMaxH[r];
      this.stats.touched++;
    }
  }

  // Same rule as wallRows (a row closes when the next item does not fit), then size each new row.
  // Rows before `start` stay as they are.
  private buildWallRows(start: number): void {
    const n = this.aspects.length;
    const prev = this.rows[this.rows.length - 1];
    const fromRow = this.rows.length;
    let first = start;
    let count = 0;
    let curW = 0;
    for (let i = start; i < n; i++) {
      const itemW = this.aspects[i] * this.size;
      if (count === 0) {
        count = 1;
        curW = itemW;
      } else if (curW + WALL_GAP + itemW <= this.width) {
        count++;
        curW += WALL_GAP + itemW;
      } else {
        this.rows.push({ start: first, end: i, top: 0, h: 0 });
        first = i;
        count = 1;
        curW = itemW;
      }
      this.stats.touched++;
    }
    if (count > 0) this.rows.push({ start: first, end: n, top: 0, h: 0 });
    let top = prev ? prev.top + prev.h + WALL_GAP : 0;
    for (let r = fromRow; r < this.rows.length; r++) {
      const row = this.rows[r];
      row.top = top;
      row.h = this.wallRowH(r);
      top += row.h + WALL_GAP;
    }
  }

  private wallRowH(r: number): number {
    const row = this.rows[r];
    let sum = 0;
    for (let i = row.start; i < row.end; i++) sum += this.aspects[i];
    const gaps = WALL_GAP * (row.end - row.start - 1);
    const stretched = (this.width - gaps) / sum;
    if (r < this.rows.length - 1) return stretched;
    // The open last row keeps the natural height, unless one wide item overflows the container.
    return sum * this.size + gaps > this.width ? stretched : this.size;
  }

  private settleFrom(r: number): void {
    for (let k = r; k < this.rows.length; k++) {
      const row = this.rows[k];
      if (k > r) row.top = this.rows[k - 1].top + this.rows[k - 1].h + this.rowGap();
      row.h = this.rowMaxH[k];
    }
  }

  private pushRowRects(r: number, out: Placed[]): void {
    const row = this.rows[r];
    if (this.mode === "wall") {
      let x = 0;
      for (let i = row.start; i < row.end; i++) {
        const w = this.aspects[i] * row.h;
        out.push({ index: i, rect: { x, y: row.top, w, h: row.h } });
        x += w + WALL_GAP;
      }
      return;
    }
    const colGap = this.mode === "grid" ? GRID_GAP : 0;
    for (let i = row.start; i < row.end; i++) {
      out.push({ index: i, rect: { x: (i - row.start) * (this.cw + colGap), y: row.top, w: this.cw, h: row.h } });
    }
  }
}
