import type { Api, LibraryItem, WebItem } from "../api/client";
import { getWebPage, setWebPage } from "./webProgress";

export interface ReaderLoad {
  title: string;
  count: number;
  tpl: string;
  thumbTpl: string | null;
  start: number;
  books: LibraryItem[];
  notice: string | null;
  save?: { item: WebItem };
}

export interface ReaderSource {
  kind: "komga" | "web";
  key: string;
  load(): Promise<ReaderLoad>;
  saveProgress(page: number, count: number, opts?: { keepalive?: boolean }): void;
  backTarget(): string;
}

function startPage(p: string | null, saved: number | null | undefined, count: number | null): number {
  if (p) return Number(p);
  return !saved || saved <= 1 || (count != null && saved >= count) ? 1 : saved;
}

export function komgaSource(api: Api, bookId: string, query: URLSearchParams): ReaderSource {
  const seriesId = query.get("series");
  return {
    kind: "komga",
    key: bookId,
    async load() {
      const [d, series] = await Promise.all([
        api.getItem("books", bookId),
        seriesId
          ? api.getItem("series", seriesId).then(
              (s) => ({ books: s.books ?? [], notice: s.notice?.message ?? null }),
              () => ({ books: [] as LibraryItem[], notice: null }),
            )
          : Promise.resolve({ books: [] as LibraryItem[], notice: null }),
      ]);
      return {
        title: d.title,
        count: d.page_count ?? 0,
        tpl: d.page_url ?? "",
        thumbTpl: d.page_thumb_url ?? null,
        start: startPage(query.get("p"), d.read_page, d.page_count ?? null),
        books: series.books,
        notice: series.notice,
      };
    },
    saveProgress(page, _count, opts) {
      void api.saveProgress(bookId, page, undefined, opts).catch(() => {});
    },
    backTarget() {
      return seriesId ? "/item/series/" + encodeURIComponent(seriesId) : "/item/books/" + encodeURIComponent(bookId);
    },
  };
}

export function webSource(api: Api, source: string, id: string, query: URLSearchParams): ReaderSource {
  const key = source + ":" + id;
  return {
    kind: "web",
    key,
    async load() {
      if (source !== "nhentai") throw new Error("unsupported source");
      const b = await api.webBook(source, id);
      const count = b.page_count;
      return {
        title: b.title_main || b.title || "",
        count,
        tpl: b.page_url,
        thumbTpl: b.page_thumb_url,
        start: startPage(query.get("p"), getWebPage(key), count),
        books: [],
        notice: null,
        save: { item: b.item },
      };
    },
    saveProgress(page, count) {
      setWebPage(key, page, count);
    },
    backTarget() {
      return "/";
    },
  };
}
