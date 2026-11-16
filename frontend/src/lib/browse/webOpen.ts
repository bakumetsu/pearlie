// webOpen: parse and build the web=<source>:<post_id> URL param that opens a booru post in the lightbox
import type { Api, WebItem } from "../api/client";

// Sites whose posts have no page of their own (nhentai has /web/nhentai/<id>).
const BOORU = ["danbooru", "gelbooru", "rule34"];

export type WebRef = { source: string; postId: string };

export function parseWeb(query: URLSearchParams): WebRef | null {
  const raw = query.get("web");
  if (raw === null) return null;
  const at = raw.indexOf(":");
  if (at < 0) return null;
  const source = raw.slice(0, at);
  const postId = raw.slice(at + 1);
  if (!BOORU.includes(source)) return null;
  if (!/^\d+$/.test(postId)) return null;
  return { source, postId };
}

export function webKey(source: string, postId: string): string {
  return `${source}:${postId}`;
}

export function withWeb(query: URLSearchParams, key: string | null): string {
  const next = new URLSearchParams(query.toString());
  const ref = key === null ? null : parseWeb(new URLSearchParams({ web: key }));
  if (ref) next.set("web", webKey(ref.source, ref.postId));
  else next.delete("web");
  return next.toString();
}

// Link target of a booru tile: the current page with the post in the address. Other sites have their own page.
export function webTileHref(path: string, query: URLSearchParams, w: { source: string; post_id: string }): string | undefined {
  if (!BOORU.includes(w.source)) return undefined;
  return path + "?" + withWeb(query, webKey(w.source, w.post_id));
}

// A post outside the loaded grid: ask the search for it by id, limited to its site, so the throttle,
// safe mode and tag rules still apply. Null when the site hides it or the call fails.
export async function fetchWebPost(api: Pick<Api, "search">, ref: WebRef, signal?: AbortSignal): Promise<WebItem | null> {
  try {
    const r = await api.search({ q: `id:${ref.postId}`, sources: [ref.source], page: 1, page_size: 1 }, signal);
    for (const s of r.sections ?? []) {
      for (const it of s.items ?? []) {
        if ("post_id" in it && it.source === ref.source && it.post_id === ref.postId) return it;
      }
    }
  } catch {
    // fall through: the caller shows "Post not available"
  }
  return null;
}
