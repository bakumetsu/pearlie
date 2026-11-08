export type Rect = { x: number; y: number; w: number; h: number };
export type Viewport = { w: number; h: number };
export type PlayerMode = "hidden" | "mini" | "stage";

export const RAIL_W = 72;
export const DOCK_H = 72;
export const DOCK_VIDEO = { w: 96, h: 54 };
export const DOCK_PAD = 9; // (DOCK_H - DOCK_VIDEO.h) / 2 vertical, also used as left padding after the rail

export function dockBarRect(vp: Viewport): Rect {
  return { x: RAIL_W, y: vp.h - DOCK_H, w: vp.w - RAIL_W, h: DOCK_H };
}

export function dockVideoRect(vp: Viewport): Rect {
  return {
    x: RAIL_W + DOCK_PAD + 3,
    y: vp.h - DOCK_H + DOCK_PAD,
    w: DOCK_VIDEO.w,
    h: DOCK_VIDEO.h,
  };
}

export function rectFor(mode: PlayerMode, slot: Rect | null, vp: Viewport): Rect | null {
  if (mode === "hidden") return null;
  if (mode === "mini") return dockVideoRect(vp);
  // stage: use slot when valid, else fall back to dock
  if (slot !== null && slot.w > 0 && slot.h > 0) return slot;
  return dockVideoRect(vp);
}

export function rectsEqual(a: Rect | null, b: Rect | null): boolean {
  if (a === null || b === null) return a === null && b === null;
  const TOL = 0.5;
  return (
    Math.abs(a.x - b.x) <= TOL &&
    Math.abs(a.y - b.y) <= TOL &&
    Math.abs(a.w - b.w) <= TOL &&
    Math.abs(a.h - b.h) <= TOL
  );
}

export function toTransform(r: Rect): string {
  const x = Math.round(r.x * 100) / 100;
  const y = Math.round(r.y * 100) / 100;
  return `translate(${x}px, ${y}px)`;
}

export function modeOnLeave(playing: boolean): PlayerMode {
  return playing ? "mini" : "hidden";
}

export function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
