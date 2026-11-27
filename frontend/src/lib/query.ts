
export type Chip = { raw: string; exclude: boolean; scope: string | null; value: string };
export type Pill = "all" | "images" | "videos" | "books" | "web";
export type SectionId =
  | "stash_images"
  | "stash_videos"
  | "stump_books"
  | "danbooru"
  | "gelbooru"
  | "rule34"
  | "nhentai";
export type SiteId = "danbooru" | "gelbooru" | "rule34" | "nhentai";
/** `all`: the All pill (the merged row). Left out = false, for states built without it. */
export type SearchState = { chips: Chip[]; pill: Pill; sites: SiteId[]; all?: boolean };

export type ChipKind = "tag" | "title" | "id";

/** What a chip stands for: the scopes `title` and `id` are reserved and never tags. */
export function chipKind(chip: Chip): ChipKind {
  if (chip.scope === "title") return "title";
  if (chip.scope === "id") return "id";
  return "tag";
}

/** Text shown on a chip: a title chip drops its quotes, like `title:big dragon`. */
export function chipLabel(chip: Chip): string {
  if (chipKind(chip) !== "title") return chip.raw;
  return `${chip.exclude ? "-" : ""}title:${chip.value}`;
}

/** Label for the remove button. */
export function chipRemoveLabel(chip: Chip): string {
  if (chipKind(chip) !== "title") return `Remove ${chip.raw}`;
  return `Remove ${chip.exclude ? "excluded " : ""}title ${chip.value}`;
}

/** True while text has a quote that is not closed yet (a comma must not commit then). */
export function hasOpenQuote(text: string): boolean {
  return (text.match(/"/g) ?? []).length % 2 === 1;
}

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
  // A fully quoted token, or `title:` plus a value, is a title chip (never a tag).
  if (rest.startsWith('"') || rest.startsWith("title:")) {
    const text = rest.startsWith('"') ? rest : rest.slice("title:".length);
    const title = text.replaceAll('"', "").trim();
    if (title === "") return null;
    return {
      raw: `${exclude ? "-" : ""}title:"${title}"`,
      exclude,
      scope: "title",
      value: title,
    };
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

/** nhentai book id from a lone "177013" or "id:177013" token, else null. */
export function nhentaiIdOf(text: string): string | null {
  const m = /^(?:id:)?([1-9]\d*)$/i.exec(text.trim());
  return m ? m[1] : null;
}

/** Split text on whitespace and commas, but not inside quotes; quotes stay in the token. */
export function splitInput(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (const ch of text) {
    if (ch === '"') {
      quoted = !quoted;
      cur += ch;
    } else if (!quoted && (ch === "," || /\s/.test(ch))) {
      if (cur !== "") out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur !== "") out.push(cur);
  return out;
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
  "stump_books",
];

/** Resolve the active section ids for a pill and site selection. An empty query leaves the library rows out (the Library page has them). */
export function sectionsFor(pill: Pill, sites: SiteId[], emptyQuery = false): SectionId[] {
  switch (pill) {
    case "all":
      // The selected sites' rows come first, with or without chips; library rows below.
      return emptyQuery ? [...sites] : [...sites, ...LIBRARY_SECTIONS];
    case "images":
      return ["stash_images"];
    case "videos":
      return ["stash_videos"];
    case "books":
      return ["stump_books"];
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
  // The first visit (no sites and no all in the address) starts with All.
  const all = params.get("all") === "1" || (sitesRaw === null && !params.has("all"));
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

  return { chips, pill, sites, all };
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
  if (s.all) {
    params.set("all", "1");
  } else {
    // Without All the sites are always written: an address without them means the first visit (All).
    const sameSites =
      s.sites.length === DEFAULT_SITES.length &&
      s.sites.every((v, i) => v === DEFAULT_SITES[i]);
    if (s.all === false || !sameSites) params.set("sites", s.sites.join(","));
  }
  const str = params.toString();
  return str ? `?${str}` : "";
}

/** Search URL for one tapped tag, on the same source (pill) the tag came from. */
export function tagSearchHref(name: string, pill: Pill = "all"): string {
  const chip = parseChip(name.trim().replace(/\s+/g, "_"));
  const chips = chip ? [chip] : [];
  return "/" + buildSearchParams({ chips, pill, sites: DEFAULT_SITES });
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

/** The sites in the saved order; a site the order lacks goes last in the default order. */
export function orderedSites(order: readonly string[] | undefined): SiteId[] {
  const all = SITE_ORDER.map((d) => d.id);
  const known = (order ?? []).filter((id): id is SiteId => (all as string[]).includes(id));
  const first = [...new Set(known)];
  return [...first, ...all.filter((id) => !first.includes(id))];
}

/** Move one site to where another sits; sites that are not shown keep their place. */
export function moveSite(order: readonly SiteId[], id: SiteId, target: SiteId): SiteId[] {
  const from = order.indexOf(id);
  const to = order.indexOf(target);
  if (from < 0 || to < 0 || from === to) return [...order];
  const next = order.filter((x) => x !== id);
  next.splice(to, 0, id);
  return next;
}

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
  if (!s.all && !isDefaultSites(s.sites)) {
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

/** Sites to show: hidden ones drop out; a selection that was only hidden sites falls back to the first visible one. */
export function effectiveSites(sites: SiteId[], hidden: readonly string[]): SiteId[] {
  const shown = sites.filter((id) => !hidden.includes(id));
  if (shown.length > 0 || sites.length === 0) return shown;
  const first = SITE_ORDER.find((d) => !hidden.includes(d.id));
  return first ? [first.id] : [];
}
