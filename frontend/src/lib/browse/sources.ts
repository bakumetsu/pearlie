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
  const width = (item as { width?: number | null }).width;
  const height = (item as { height?: number | null }).height;
  return fallbackAspect(kind, width, height);
}
