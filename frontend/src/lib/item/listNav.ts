import type { LibraryItem, WebItem } from "../api/client";
import { keyOf } from "../stores/shared.svelte";
import type { SingularKind } from "./kinds";

export interface ListGrid {
  items: (LibraryItem | WebItem)[];
  page: number;
  pages: number | null;
  hasNext: boolean;
  status: string;
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

export function pageEdge(grid: ListGrid, dir: Dir): boolean {
  if (dir === 1) return grid.hasNext || (grid.pages !== null && grid.page < grid.pages);
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
      await grid.goTo(grid.page + dir);
      if (grid.status === "error") break;
      const items = grid.items;
      const result = nearestInList(items, dir === 1 ? -1 : items.length, dir, opts.kind);
      if (result) {
        grid.markCrossed();
        return result;
      }
    }
    if (grid.page !== origPage) {
      await grid.goTo(origPage);
    }
    return null;
  } finally {
    stepping.delete(grid);
  }
}
