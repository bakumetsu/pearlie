import type { SiteId } from "../query";

// The site pill tapped last, kept for this session only (not saved).
export const tappedSite = $state<{ id: SiteId | null }>({ id: null });

export function firstTapped(sites: SiteId[], id: SiteId | null, on: boolean): SiteId[] {
  if (!on || id === null || !sites.includes(id)) return sites;
  return [id, ...sites.filter((s) => s !== id)];
}
