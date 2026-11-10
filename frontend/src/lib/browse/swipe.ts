// swipe: pure horizontal-swipe classifier for the wall overlay (T-67)

export const SWIPE_MIN = 60;
export const SWIPE_RATIO = 1.5;

export function swipeDir(dx: number, dy: number): 1 | -1 | null {
  if (Math.abs(dx) <= SWIPE_MIN) return null;
  if (Math.abs(dx) <= SWIPE_RATIO * Math.abs(dy)) return null;
  return dx < 0 ? 1 : -1;
}
