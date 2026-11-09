export type PageStats = { megapixels: number | null; size_bytes: number | null };

function formatThousands(n: number): string {
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function formatGiB(sizeBytes: number): string {
  const gib = sizeBytes / (1024 ** 3);
  return gib.toFixed(1) + " GiB";
}

export function rangeText(opts: {
  page: number;
  perPage: number;
  shown: number;
  total: number | null;
  stats: PageStats | null;
}): string {
  const { page, perPage, shown, total, stats } = opts;
  if (shown <= 0) return "";

  const a = (page - 1) * perPage + 1;
  const b = a + shown - 1;

  let text: string;
  if (total === null) {
    text = `${a}-${b}`;
  } else {
    text = `${a}-${b} of ${total}`;
  }

  if (stats !== null) {
    const parts: string[] = [];
    if (stats.megapixels !== null) {
      parts.push(formatThousands(stats.megapixels) + " Megapixels");
    }
    if (stats.size_bytes !== null) {
      parts.push(formatGiB(stats.size_bytes));
    }
    if (parts.length > 0) {
      text += ` (${parts.join(" - ")})`;
    }
  }

  return text;
}

export type PagerForm = "full" | "reduced";

export function pagerForm(pages: number | null): PagerForm {
  return typeof pages === "number" ? "full" : "reduced";
}

export function pageOptions(pages: number): { kind: "select"; values: number[] } | { kind: "field" } {
  if (pages <= 200) {
    return { kind: "select", values: Array.from({ length: pages }, (_, i) => i + 1) };
  }
  return { kind: "field" };
}

export function pagerState(opts: {
  page: number;
  pages: number | null;
  hasNext: boolean;
}): { first: boolean; prev: boolean; next: boolean; last: boolean; showLast: boolean } {
  const { page, pages, hasNext } = opts;

  if (typeof pages === "number") {
    return {
      first: page > 1,
      prev: page > 1,
      next: page < pages,
      last: page < pages,
      showLast: true,
    };
  }

  return {
    first: page > 1,
    prev: page > 1,
    next: hasNext,
    last: false,
    showLast: false,
  };
}

export function remapPage(firstIndex: number, newPerPage: number): number {
  return Math.max(1, Math.floor((firstIndex - 1) / newPerPage) + 1);
}

export function clampInput(value: string, max: number): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = parseInt(trimmed, 10);
  if (n < 1 || n > max) return null;
  return n;
}

export function pageOf(raw: string | null): number {
  if (raw === null) return 1;
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return 1;
  const n = parseInt(trimmed, 10);
  return n >= 1 ? n : 1;
}
