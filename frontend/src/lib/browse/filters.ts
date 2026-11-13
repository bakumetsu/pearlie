// Web-site filter state for the See-all toolbar (design D-16). URL form: order=score, rating=g,s.
// Defaults (newest, any rating) are omitted from the URL.

export const ORDER_LABELS: Record<string, string> = { newest: "Newest", score: "Top score" };
export const RATING_LABELS: Record<string, string> = {
  g: "General",
  s: "Sensitive",
  q: "Questionable",
  e: "Explicit",
};

// Used until /api/search/filters answers (or when it fails): the contract's web-site defaults.
export const DEFAULT_ORDERS = ["newest", "score"];
export const DEFAULT_RATINGS = ["g", "s", "q", "e"];

export function parseOrder(v: string | null): string {
  return v === "score" ? "score" : "";
}

// Known values only, in canonical order, no duplicates.
export function parseRating(v: string | null): string[] {
  if (!v) return [];
  const set = new Set(v.split(","));
  return DEFAULT_RATINGS.filter((r) => set.has(r));
}
