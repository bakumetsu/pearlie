import type { SiteId } from "../query";

const KEY = "pearlie.search.sites";
const VALID: readonly string[] = ["danbooru", "gelbooru", "rule34", "nhentai"];

type SiteStorage = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): SiteStorage | undefined {
  try {
    return typeof localStorage !== "undefined" ? localStorage : undefined;
  } catch {
    return undefined;
  }
}

/** The site pills last chosen on this device, or undefined when none were saved. */
export function readSites(storage: SiteStorage | undefined = defaultStorage()): SiteId[] | undefined {
  try {
    const raw = storage?.getItem(KEY);
    if (raw === null || raw === undefined) return undefined;
    return raw === "" ? [] : raw.split(",").filter((s): s is SiteId => VALID.includes(s));
  } catch {
    return undefined;
  }
}

/** Remember the site pills per device. */
export function writeSites(sites: SiteId[], storage: SiteStorage | undefined = defaultStorage()): void {
  try {
    storage?.setItem(KEY, sites.join(","));
  } catch { /* storage blocked: the choice lasts until reload */ }
}
