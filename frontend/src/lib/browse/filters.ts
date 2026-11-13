// Web-site filter state for the See-all toolbar (design D-16). URL form: order=score, rating=g,s.
// Defaults (newest, any rating) are omitted from the URL.

export const ORDER_LABELS: Record<string, string> = { newest: "Newest", score: "Top score" };
export const RATING_LABELS: Record<string, string> = {
  g: "General",
  s: "Sensitive",
  q: "Questionable",
  e: "Explicit",
};

// Fallback lists while /api/search/filters has not answered (or failed): the contract's web-site defaults.
export const DEFAULT_ORDERS = ["newest", "score"];
export const DEFAULT_RATINGS = ["g", "s", "q", "e"];

// A non-default order the site lists; "" (newest) is the default and stays out of the URL.
export function parseOrder(v: string | null, allowed: string[] = DEFAULT_ORDERS): string {
  return v && v !== "newest" && allowed.includes(v) ? v : "";
}

// Values the site lists only, in the site's order, no duplicates.
export function parseRating(v: string | null, allowed: string[] = DEFAULT_RATINGS): string[] {
  if (!v) return [];
  const set = new Set(v.split(","));
  return allowed.filter((r) => set.has(r));
}
