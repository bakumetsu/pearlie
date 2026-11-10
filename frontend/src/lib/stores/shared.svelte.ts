import { createGrid } from "./grid.svelte";
import type { LibraryItem, WebItem } from "../api/client";
import type { Kind } from "../item/kinds";

export function keyOf(t: LibraryItem | WebItem): string {
  return "post_id" in t ? t.source + ":" + t.post_id : t.kind + ":" + t.id;
}

const grids: Record<string, ReturnType<typeof createGrid<LibraryItem | WebItem>>> = {};

// One list per kind so image and video item nav each walk their own list;
// the "web" grid is shared by all web sources, they overwrite each other,
// which is fine since they have no item page.
export function gridFor(kind: Kind | null) {
  const key = kind ?? "web";
  let g = grids[key];
  if (!g) {
    g = createGrid<LibraryItem | WebItem>(keyOf);
    grids[key] = g;
  }
  return g;
}

export function resetAllGrids(): void {
  for (const g of Object.values(grids)) g.reset();
}
