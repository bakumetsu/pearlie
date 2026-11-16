import { describe, it, expect } from "vitest";
import { isFinished, pickContinue, seriesRatio } from "./seriesProgress";
import type { LibraryItem } from "../api/client";

const b = (id: string, read_page?: number, page_count?: number) => ({ id, read_page, page_count }) as LibraryItem;

describe("seriesProgress", () => {
  it("isFinished needs read_page and page_count and read_page >= page_count", () => {
    expect(isFinished(b("a", 10, 10))).toBe(true);
    expect(isFinished(b("a", 3, 10))).toBe(false);
    expect(isFinished(b("a", undefined, 10))).toBe(false);
    expect(isFinished(b("a", 3, undefined))).toBe(false);
  });

  it("pickContinue returns the first unfinished book", () => {
    const books = [b("a", 10, 10), b("b", 4, 10), b("c")];
    expect(pickContinue(books)?.id).toBe("b");
  });

  it("pickContinue returns null when all are finished or the list is empty", () => {
    expect(pickContinue([b("a", 10, 10)])).toBeNull();
    expect(pickContinue([])).toBeNull();
  });

  it("seriesRatio divides read by total and hides on missing data", () => {
    expect(seriesRatio(2, 4)).toBe(0.5);
    expect(seriesRatio(0, 4)).toBe(0);
    expect(seriesRatio(undefined, 4)).toBeUndefined();
    expect(seriesRatio(2, 0)).toBeUndefined();
    expect(seriesRatio(2, null)).toBeUndefined();
  });
});
