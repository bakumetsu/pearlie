import type { LibraryItem, WebItem } from "../api/client";
import { fallbackAspect } from "./layout";

export const WEB_SOURCES: readonly string[] = ["danbooru", "gelbooru", "rule34", "nhentai"];

export function isWebSource(source: string): boolean {
  return WEB_SOURCES.includes(source);
}

export function itemKind(item: LibraryItem | WebItem): string | undefined {
  return "post_id" in item ? undefined : (item as LibraryItem).kind;
}

export function itemAspect(item: LibraryItem | WebItem): number {
  const rawKind = itemKind(item);
  const kind =
    rawKind === "image"
      ? "images"
      : rawKind === "video"
        ? "video"
        : rawKind === "series"
          ? "series"
          : rawKind === "book"
            ? "books"
            : undefined;
  // Mirrors Tile.svelte: an nhentai cover is always 2:3, whatever size the post reports.
  if ("post_id" in item && item.source === "nhentai") return 2 / 3;
  const width = (item as { width?: number | null }).width;
  const height = (item as { height?: number | null }).height;
  return fallbackAspect(kind, width, height);
}

// Caption lines a tile shows under its picture, so the virtual layout sizes grid and list rows
// from data. Mirrors Tile.svelte (title and meta line); keep the two in step. Each part is one line.
export function captionLines(item: LibraryItem | WebItem, variant: "grid" | "list" = "list"): number {
  if ("post_id" in item) {
    if (variant === "grid") return 0;
    return 1 + ((item as WebItem).title ? 1 : 0);
  }
  const l = item as LibraryItem;
  if (variant === "grid") return l.kind === "image" ? 0 : 1;
  const hasMeta =
    (l.width != null && l.height != null) ||
    (l.kind === "video" && l.duration_s != null) ||
    (l.kind === "book" && l.page_count != null) ||
    (l.kind === "series" && l.book_count != null) ||
    l.rating != null;
  return 1 + (hasMeta ? 1 : 0);
}
