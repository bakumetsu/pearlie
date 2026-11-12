import type { LibraryItem, WebItem } from "../api/client";
import { keyOf } from "../stores/shared.svelte";
import type { SingularKind } from "./kinds";

export interface ListGrid {
  items: (LibraryItem | WebItem)[];
  page: number;
  pages: number | null;
  hasNext: boolean;
  status: string;
  nextPage?: number;
  more?: string;
  goTo(page: number): Promise<void>;
  markCrossed(): void;
}

export type Dir = 1 | -1;

export type StepOpts = { kind?: SingularKind | null; cross: boolean; maxPages?: number };

export function nearestInList(
  items: (LibraryItem | WebItem)[],
  fromIdx: number,
  dir: Dir,
  kind?: SingularKind | null,
): LibraryItem | null {
  let i = fromIdx + dir;
  while (i >= 0 && i < items.length) {
    const item = items[i]!;
    if ("post_id" in item) {
      i += dir;
      continue;
    }
    if (kind != null && (item as LibraryItem).kind !== kind) {
      i += dir;
      continue;
    }
    return item as LibraryItem;
  }
  return null;
}

// Index to search from after stepping onto another page: an appended page (infinite scroll) keeps
// the old items in front, so the search starts at the old end instead of at the list edge.
export function arrivalIdx(grid: ListGrid, dir: Dir, firstKey: string | null, prevLen: number): number {
  const first = grid.items[0];
  const appended = dir === 1 && firstKey !== null && first !== undefined && keyOf(first) === firstKey && grid.items.length > prevLen;
  if (appended) return prevLen - 1;
  return dir === 1 ? -1 : grid.items.length;
}

export function stepTarget(grid: ListGrid, dir: Dir): number {
  return dir === 1 ? (grid.nextPage ?? grid.page + 1) : grid.page - 1;
}

export function pageEdge(grid: ListGrid, dir: Dir): boolean {
  if (dir === 1) return grid.hasNext || (grid.pages !== null && (grid.nextPage ?? grid.page + 1) <= grid.pages);
  return grid.page > 1;
}

export function canStep(grid: ListGrid, fromKey: string, dir: Dir, opts: StepOpts): boolean {
  const idx = grid.items.findIndex((t) => keyOf(t) === fromKey);
  if (idx < 0) return false;
  if (nearestInList(grid.items, idx, dir, opts.kind)) return true;
  return opts.cross && pageEdge(grid, dir);
}

const stepping = new WeakSet<object>();

export async function stepInList(
  grid: ListGrid,
  fromKey: string,
  dir: Dir,
  opts: StepOpts,
): Promise<LibraryItem | null> {
  const idx = grid.items.findIndex((t) => keyOf(t) === fromKey);
  if (idx < 0) return null;
  const found = nearestInList(grid.items, idx, dir, opts.kind);
  if (found) return found;
  if (!opts.cross) return null;

  if (stepping.has(grid)) return null;
  stepping.add(grid);
  try {
    const origPage = grid.page;
    const maxPages = opts.maxPages ?? 3;
    for (let i = 0; i < maxPages; i++) {
      if (!pageEdge(grid, dir)) break;
      const firstKey = grid.items[0] ? keyOf(grid.items[0]) : null;
      const prevLen = grid.items.length;
      await grid.goTo(stepTarget(grid, dir));
      if (grid.status === "error" || grid.more === "error") break;
      const items = grid.items;
      const result = nearestInList(items, arrivalIdx(grid, dir, firstKey, prevLen), dir, opts.kind);
      if (result) {
        grid.markCrossed();
        return result;
      }
    }
    if (grid.page !== origPage && grid.more !== "error") {
      await grid.goTo(origPage);
    }
    return null;
  } finally {
    stepping.delete(grid);
  }
}
