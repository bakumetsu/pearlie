// Scroll-driven hide/show of the See-all toolbar: hide on scroll down, show on scroll up.
export const AUTOHIDE_DELTA = 12;
export const AUTOHIDE_TOP = 80;

// Returns the next hidden state and the scroll position to compare against next time.
export function nextAutohide(
  hidden: boolean,
  lastY: number,
  y: number,
  blocked: boolean,
): { hidden: boolean; lastY: number } {
  if (blocked || y <= AUTOHIDE_TOP) return { hidden: false, lastY: y };
  const dy = y - lastY;
  if (Math.abs(dy) < AUTOHIDE_DELTA) return { hidden, lastY };
  return { hidden: dy > 0, lastY: y };
}
