import { createGrid } from "./grid.svelte";
import type { LibraryItem, WebItem } from "../api/client";

export function keyOf(t: LibraryItem | WebItem): string {
  return "post_id" in t ? t.source + ":" + t.post_id : t.kind + ":" + t.id;
}

export const seeAllGrid = createGrid<LibraryItem | WebItem>(keyOf);
