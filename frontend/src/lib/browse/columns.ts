export const RAIL_MIN_WIDTH = 900;

export type RailRange = { base: number; minTile: number; maxTile: number };

export const RAIL_IMAGE: RailRange = { base: 7, minTile: 156, maxTile: 220 };
export const RAIL_VIDEO: RailRange = { base: 5, minTile: 220, maxTile: 300 };

export function railColumns(
  width: number,
  base: number,
  maxTile: number,
  gap: number,
  minTile = 0,
): number {
  if (!(width > 0)) return base;
  const wanted = Math.max(base, Math.ceil((width + gap) / (maxTile + gap)));
  const fit = Math.max(base, Math.floor((width + gap) / (minTile + gap)));
  return Math.min(wanted, fit);
}
