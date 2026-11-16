import type { LibraryItem } from "../api/client";

// A book is finished when its read page reached its page count. Missing data means not finished.
export function isFinished(b: Pick<LibraryItem, "read_page" | "page_count">): boolean {
  return typeof b.read_page === "number" && typeof b.page_count === "number" && b.read_page >= b.page_count;
}

// The first book (list order) that is not finished.
export function pickContinue(books: LibraryItem[]): LibraryItem | null {
  return books.find((b) => !isFinished(b)) ?? null;
}

// Read share of a series, 0-1. Undefined when the counts are missing or the series is empty.
export function seriesRatio(readCount?: number | null, bookCount?: number | null): number | undefined {
  if (typeof readCount !== "number" || typeof bookCount !== "number" || bookCount <= 0) return undefined;
  return Math.min(1, Math.max(0, readCount / bookCount));
}
