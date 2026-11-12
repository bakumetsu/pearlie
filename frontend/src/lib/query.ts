
export type Chip = { raw: string; exclude: boolean; scope: string | null; value: string };
export type Pill = "all" | "images" | "videos" | "books" | "web";
export type SectionId =
  | "stash_images"
  | "stash_videos"
  | "komga_books"
  | "danbooru"
  | "gelbooru"
  | "rule34"
  | "nhentai";
export type SiteId = "danbooru" | "gelbooru" | "rule34" | "nhentai";
export type SearchState = { chips: Chip[]; pill: Pill; sites: SiteId[] };

/** Parse a single token into a Chip, or null if invalid. */
export function parseChip(token: string): Chip | null {
  const t = token.trim();
  if (t === "" || t === "-") return null;
  let exclude = false;
  let rest = t;
  if (rest.startsWith("-")) {
    exclude = true;
    rest = rest.slice(1);
  }
  let scope: string | null = null;
  let value: string;
  const idx = rest.indexOf(":");
  if (idx > 0 && idx < rest.length - 1) {
    scope = rest.slice(0, idx);
    value = rest.slice(idx + 1);
  } else {
    value = rest;
  }
  const raw = (exclude ? "-" : "") + (scope ? `${scope}:${value}` : value);
  return { raw, exclude, scope, value };
}

/** Split text on whitespace and commas, dropping empty tokens. */
export function splitInput(text: string): string[] {
  return text.split(/[\s,]+/).filter((t) => t !== "");
}

/** Append parsed chips from text, skipping duplicates by raw. */
export function commitText(chips: Chip[], text: string): Chip[] {
  const existing = new Set(chips.map((c) => c.raw));
  const result = [...chips];
  for (const token of splitInput(text)) {
    const chip = parseChip(token);
    if (chip && !existing.has(chip.raw)) {
      result.push(chip);
      existing.add(chip.raw);
    }
  }
  return result;
}

/** Remove the chip at index i. */
export function removeChipAt(chips: Chip[], i: number): Chip[] {
  return chips.filter((_, idx) => idx !== i);
}

/** Remove the last chip; empty array stays empty. */
export function removeLastChip(chips: Chip[]): Chip[] {
  if (chips.length === 0) return chips;
  return chips.slice(0, -1);
}

/** Serialise chips to a space-joined string of raws. */
export function serialiseQuery(chips: Chip[]): string {
  return chips.map((c) => c.raw).join(" ");
}

/** Parse a serialised query string into chips. */
export function parseQuery(q: string): Chip[] {
  return commitText([], q);
}

/** Default sites list. */
export const DEFAULT_SITES: SiteId[] = ["danbooru"];

/** Sections that belong to local libraries. */
export const LIBRARY_SECTIONS: SectionId[] = [
  "stash_images",
  "stash_videos",
  "komga_books",
];

/** Resolve the active section ids for a pill and site selection. */
export function sectionsFor(pill: Pill, sites: SiteId[]): SectionId[] {
  switch (pill) {
    case "all":
      return [...LIBRARY_SECTIONS, ...sites];
    case "images":
      return ["stash_images"];
    case "videos":
      return ["stash_videos"];
    case "books":
      return ["komga_books"];
    case "web":
      return sites;
  }
}

const VALID_PILLS: Pill[] = ["all", "images", "videos", "books", "web"];
const VALID_SITES: SiteId[] = ["danbooru", "gelbooru", "rule34", "nhentai"];

/** Parse a location.search string into a SearchState. */
export function parseSearchParams(search: string): SearchState {
  const params = new URLSearchParams(search);

  const q = params.get("q");
  const chips = q ? parseQuery(q) : [];

  const src = params.get("src");
  const pill: Pill =
    src && (VALID_PILLS as string[]).includes(src) ? (src as Pill) : "all";

  const sitesRaw = params.get("sites");
  let sites: SiteId[];
  if (sitesRaw === null) {
    sites = DEFAULT_SITES;
  } else if (sitesRaw === "") {
    sites = [];
  } else {
    sites = sitesRaw
      .split(",")
      .filter((s): s is SiteId => (VALID_SITES as string[]).includes(s));
  }

  return { chips, pill, sites };
}

/** Build a location.search string from a SearchState. */
export function buildSearchParams(s: SearchState): string {
  const params = new URLSearchParams();
  if (s.chips.length > 0) {
    params.set("q", serialiseQuery(s.chips));
  }
  if (s.pill !== "all") {
    params.set("src", s.pill);
  }
  const sameSites =
    s.sites.length === DEFAULT_SITES.length &&
    s.sites.every((v, i) => v === DEFAULT_SITES[i]);
  if (!sameSites) {
    params.set("sites", s.sites.join(","));
  }
  const str = params.toString();
  return str ? `?${str}` : "";
}

/** True when the web pill has no query chips. */
export function webNeedsQuery(s: SearchState): boolean {
  return s.chips.length === 0;
}

export const PILLS: { id: Pill; label: string }[] = [
  { id: "all", label: "All" },
  { id: "images", label: "Images" },
  { id: "videos", label: "Videos" },
  { id: "books", label: "Books" },
  { id: "web", label: "Web" },
];

export const SITE_ORDER: { id: SiteId; label: string }[] = [
  { id: "danbooru", label: "Danbooru" },
  { id: "gelbooru", label: "Gelbooru" },
  { id: "rule34", label: "Rule34" },
  { id: "nhentai", label: "nhentai" },
];

export type FilterChip = { key: string; label: string; remove: Partial<SearchState> };

function isDefaultSites(sites: SiteId[]): boolean {
  return sites.length === DEFAULT_SITES.length && sites.every((v, i) => v === DEFAULT_SITES[i]);
}

/** Filters that differ from the defaults, each with the state change that clears it. */
export function filterChips(s: SearchState): FilterChip[] {
  const out: FilterChip[] = [];
  if (s.pill !== "all") {
    out.push({ key: "pill", label: PILLS.find((p) => p.id === s.pill)?.label ?? s.pill, remove: { pill: "all" } });
  }
  if (!isDefaultSites(s.sites)) {
    if (s.sites.length === 0) {
      out.push({ key: "sites", label: "No sites", remove: { sites: DEFAULT_SITES } });
    }
    for (const id of s.sites) {
      out.push({
        key: "site:" + id,
        label: SITE_ORDER.find((d) => d.id === id)?.label ?? id,
        remove: { sites: s.sites.filter((x) => x !== id) },
      });
    }
  }
  return out;
}

/** Toggle one site, keeping the canonical site order. */
export function toggleSiteIn(sites: SiteId[], id: SiteId): SiteId[] {
  const next = sites.includes(id) ? sites.filter((s) => s !== id) : [...sites, id];
  return SITE_ORDER.map((d) => d.id).filter((x) => next.includes(x));
}
