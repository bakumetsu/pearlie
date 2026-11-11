export type BackdropWhere = "wall" | "item" | "lightbox";

export const BACKDROP_DEFAULTS = {
  strength: 60,
  wall: true,
  item: true,
  lightbox: true,
};

type BackdropValues = {
  backdrop_strength: number;
  backdrop_wall: boolean;
  backdrop_item: boolean;
  backdrop_lightbox: boolean;
};

export function backdropStrength(
  values: BackdropValues | null | undefined,
  where: BackdropWhere,
): number {
  const switchKey = `backdrop_${where}` as const;
  const on = values ? values[switchKey] : true;
  if (!on) return 0;

  const raw = values ? values.backdrop_strength : BACKDROP_DEFAULTS.strength;
  const s = Number.isFinite(raw) ? raw : BACKDROP_DEFAULTS.strength;
  return Math.min(100, Math.max(0, s));
}
