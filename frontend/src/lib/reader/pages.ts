export type ReadMode = { spread: boolean; rtl: boolean; fit: "height" | "width" };

export const DEFAULT_MODE: ReadMode = { spread: false, rtl: false, fit: "height" };

export function clampPage(p: number, count: number): number {
  if (Number.isNaN(p)) return 1;
  const max = Math.max(count, 1);
  return Math.min(Math.max(p, 1), max);
}

export function visiblePages(page: number, count: number, spread: boolean): number[] {
  const p = clampPage(page, count);
  if (!spread) return [p];
  if (p === 1) return [1];
  const pairStart = 2 + 2 * Math.floor((p - 2) / 2);
  const pairEnd = pairStart + 1;
  if (pairEnd > count) return [pairStart];
  return [pairStart, pairEnd];
}

export function nextPage(page: number, count: number, spread: boolean): number | null {
  const group = visiblePages(page, count, spread);
  const last = group[group.length - 1];
  if (last >= count) return null;
  return last + 1;
}

export function prevPage(page: number, count: number, spread: boolean): number {
  const group = visiblePages(page, count, spread);
  const first = group[0];
  if (!spread) return Math.max(first - 1, 1);
  if (first <= 2) return 1;
  return first - 2;
}

export function stepKey(key: string, rtl: boolean): "next" | "prev" | "first" | "last" | null {
  if (key === "Home") return "first";
  if (key === "End") return "last";
  if (key === "ArrowRight") return rtl ? "prev" : "next";
  if (key === "ArrowLeft") return rtl ? "next" : "prev";
  return null;
}

export function zoneAction(x: number, width: number, rtl: boolean): "next" | "prev" | "toggle" {
  if (x < 0.3 * width) return rtl ? "next" : "prev";
  if (x > 0.7 * width) return rtl ? "prev" : "next";
  return "toggle";
}

export function preloadPages(page: number, count: number, spread: boolean): number[] {
  const group = visiblePages(page, count, spread);
  const last = group[group.length - 1];
  const result: number[] = [];
  if (last + 1 <= count) result.push(last + 1);
  if (last + 2 <= count) result.push(last + 2);
  return result;
}

export function isCompleted(page: number, count: number): boolean {
  return count > 0 && page >= count;
}

export function parseMode(raw: string | null): ReadMode {
  if (raw === null) return { ...DEFAULT_MODE };
  try {
    const obj = JSON.parse(raw);
    if (typeof obj !== "object" || obj === null) return { ...DEFAULT_MODE };
    return {
      spread: typeof obj.spread === "boolean" ? obj.spread : DEFAULT_MODE.spread,
      rtl: typeof obj.rtl === "boolean" ? obj.rtl : DEFAULT_MODE.rtl,
      fit: obj.fit === "height" || obj.fit === "width" ? obj.fit : DEFAULT_MODE.fit,
    };
  } catch {
    return { ...DEFAULT_MODE };
  }
}

/** Build a page image URL from a template like "/api/media/komga/books/b1/pages/{n}". */
export function pageSrc(template: string, n: number): string {
  return template.replace("{n}", String(n));
}

