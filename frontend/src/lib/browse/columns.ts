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

// Page width at which the grid keeps today's column count (1280 px screen, rail and gutters off).
export const GRID_REF_WIDTH = 1152;
export const GRID_MAX_GROW = 1.4;

// Grid and masonry columns (D-41 3.3): up to the reference width the old floor rule; wider, columns are
// added once a tile would pass 1.4 x cell, never so many that a tile falls under cell.
export function gridColumns(width: number, cell: number, gap: number): number {
  const old = Math.max(1, Math.floor((width + gap) / (cell + gap)));
  if (!(width > GRID_REF_WIDTH)) return old;
  const base = Math.max(1, Math.floor((GRID_REF_WIDTH + gap) / (cell + gap)));
  return railColumns(width, base, cell * GRID_MAX_GROW, gap, cell);
}

// PageGrid (D-41 3.4): 5 to 8 columns, tiles fill the row.
export const PAGE_COLS_MIN = 5;
export const PAGE_COLS_MAX = 8;
export const PAGE_TILE_MIN = 120;

export function pageColumns(width: number, gap: number): number {
  if (!(width > 0)) return PAGE_COLS_MIN;
  const n = Math.floor((width + gap) / (PAGE_TILE_MIN + gap));
  return Math.min(PAGE_COLS_MAX, Math.max(PAGE_COLS_MIN, n));
}
