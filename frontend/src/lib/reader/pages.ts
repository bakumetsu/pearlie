export type Mode = "single" | "spread" | "scroll";
export type Fit = "width" | "height" | "both" | "actual";
export type Dir = "ltr" | "rtl";

export const ZOOM_STEPS = [50, 75, 100, 150, 200, 300];

export function clampPage(p: number, count: number): number {
  if (Number.isNaN(p)) return 1;
  const max = Math.max(count, 1);
  return Math.min(Math.max(p, 1), max);
}

export function isCompleted(page: number, count: number): boolean {
  return count > 0 && page >= count;
}

export function pageSrc(template: string, n: number): string {
  return template.replace("{n}", String(n));
}

export function defaultMode(_width: number, _height: number): Mode {
  return "single";
}

export function buildGroups(count: number, mode: Mode, wide: ReadonlySet<number>): number[][] {
  if (count <= 0) return [];

  if (mode === "single" || mode === "scroll") {
    const groups: number[][] = [];
    for (let i = 1; i <= count; i++) {
      groups.push([i]);
    }
    return groups;
  }

  // spread mode
  const groups: number[][] = [[1]];
  let i = 2;
  while (i <= count) {
    if (wide.has(i)) {
      groups.push([i]);
      i++;
    } else if (i + 1 > count) {
      groups.push([i]);
      i++;
    } else if (wide.has(i + 1)) {
      groups.push([i]);
      i++;
    } else {
      groups.push([i, i + 1]);
      i += 2;
    }
  }
  return groups;
}

export function groupOf(groups: number[][], page: number): number[] {
  if (groups.length === 0) return [];
  const last = groups[groups.length - 1][groups[groups.length - 1].length - 1];
  const p = clampPage(page, last);
  for (const g of groups) {
    if (p >= g[0] && p <= g[g.length - 1]) return g;
  }
  return groups[0];
}

export function displayOrder(group: number[], dir: Dir): number[] {
  if (dir === "rtl") return [...group].reverse();
  return group;
}

export function stepGroup(groups: number[][], page: number, delta: 1 | -1): number | "end" | null {
  if (groups.length === 0) return delta === 1 ? "end" : null;
  const group = groupOf(groups, page);
  const idx = groups.indexOf(group);
  const nextIdx = idx + delta;
  if (nextIdx >= groups.length) return "end";
  if (nextIdx < 0) return null;
  return groups[nextIdx][0];
}

export function preloadPages(groups: number[][], page: number): number[] {
  if (groups.length === 0) return [];
  const group = groupOf(groups, page);
  const idx = groups.indexOf(group);
  const result: number[] = [];
  if (idx + 1 < groups.length) result.push(groups[idx + 1][0]);
  if (idx + 2 < groups.length) result.push(groups[idx + 2][0]);
  return result;
}

export function zoneAction(x: number, width: number, dir: Dir): "next" | "prev" | "toggle" {
  if (x < 0.3 * width) return dir === "rtl" ? "next" : "prev";
  if (x > 0.7 * width) return dir === "rtl" ? "prev" : "next";
  return "toggle";
}

export function fitScale(
  fit: Fit,
  zoomPct: number,
  view: { w: number; h: number },
  page: { w: number; h: number },
  pagesAcross: number,
): number {
  if (view.w <= 0 || view.h <= 0 || page.w <= 0 || page.h <= 0) return 1;

  let base: number;
  switch (fit) {
    case "width":
      base = view.w / (page.w * pagesAcross);
      break;
    case "height":
      base = view.h / page.h;
      break;
    case "both":
      base = Math.min(view.w / (page.w * pagesAcross), view.h / page.h);
      break;
    case "actual":
      base = 1;
      break;
  }
  return base * zoomPct / 100;
}

export function zoomStep(zoom: number, dir: 1 | -1): number {
  if (dir === 1) {
    for (const s of ZOOM_STEPS) {
      if (s > zoom) return s;
    }
    return 300;
  } else {
    for (let i = ZOOM_STEPS.length - 1; i >= 0; i--) {
      if (ZOOM_STEPS[i] < zoom) return ZOOM_STEPS[i];
    }
    return 50;
  }
}

export type SegmentLayout = { kind: "segments"; count: number } | { kind: "track" };

export function segmentLayout(count: number, trackPx: number): SegmentLayout {
  if (count > 0 && count <= 200 && trackPx / count >= 4) {
    return { kind: "segments", count };
  }
  return { kind: "track" };
}

export function pageFromRatio(ratio: number, count: number, dir: Dir): number {
  if (count <= 0) return 1;
  const r = Math.min(Math.max(ratio, 0), 1);
  const page = Math.round(r * (count - 1)) + 1;
  const result = dir === "rtl" ? count - (page - 1) : page;
  return Math.min(Math.max(result, 1), count);
}

export const WHEEL_MIN_DELTA = 40;
export const WHEEL_MIN_GAP_MS = 350;

export function shouldWheelTurn(deltaY: number, nowMs: number, lastTurnMs: number): boolean {
  return Math.abs(deltaY) >= WHEEL_MIN_DELTA && nowMs - lastTurnMs >= WHEEL_MIN_GAP_MS;
}

export type KeyAction =
  | "next" | "prev" | "first" | "last" | "book-prev" | "book-next" | "books" | "settings" | "fit" | "mode"
  | "mode-single" | "mode-spread" | "mode-scroll" | "fullscreen" | "help" | "thumbs"
  | "zoom-in" | "zoom-out" | "zoom-reset" | "hide" | "dir" | "escape" | "scroll-up" | "scroll-down";

export function keyAction(
  e: { key: string; shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean },
  dir: Dir,
): KeyAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;

  switch (e.key) {
    case "ArrowRight": return dir === "rtl" ? "prev" : "next";
    case "ArrowLeft": return dir === "rtl" ? "next" : "prev";
    case " ": return e.shiftKey ? "prev" : "next";
    case "PageDown": return "next";
    case "PageUp": return "prev";
    case "Home": return "first";
    case "End": return "last";
    case "[": return "book-prev";
    case "]": return "book-next";
    case "b": return "books";
    case "s": return "settings";
    case "f": return "fit";
    case "F": return "fullscreen";
    case "m": return "mode";
    case "1": return "mode-single";
    case "2": return "mode-spread";
    case "3": return "mode-scroll";
    case "?": return "help";
    case "t": return "thumbs";
    case "-": return "zoom-out";
    case "+": return "zoom-in";
    case "=": return "zoom-in";
    case "0": return "zoom-reset";
    case "h": return "hide";
    case "r": return "dir";
    case "Escape": return "escape";
    case "ArrowUp": return "scroll-up";
    case "ArrowDown": return "scroll-down";
    default: return null;
  }
}
