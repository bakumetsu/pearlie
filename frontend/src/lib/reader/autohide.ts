import type { KeyAction } from "./pages";

/** Keys that open UI on purpose show the chrome; page turns and view tweaks leave it alone. */
export function keyShowsChrome(a: KeyAction | null): boolean {
  return a === "books" || a === "settings" || a === "help" || a === "thumbs";
}

/** True only for a real mouse/pen move: touch, zero delta and the first sample never count. */
export function createMoveGuard() {
  let lastX: number | null = null;
  let lastY: number | null = null;
  return (e: { clientX: number; clientY: number; pointerType?: string }): boolean => {
    const px = lastX;
    const py = lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    if (e.pointerType === "touch") return false;
    if (px === null || py === null) return false;
    return e.clientX !== px || e.clientY !== py;
  };
}

export function createAutoHide(opts: {
  delayMs?: number;
  blocked: () => boolean;
  onchange: (hidden: boolean) => void;
}) {
  let hidden = false;
  let hover = false;
  let focus = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const delay = opts.delayMs ?? 4000;

  function set(h: boolean) {
    if (hidden !== h) {
      hidden = h;
      opts.onchange(h);
    }
  }
  function clear() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }
  function start() {
    clear();
    timer = setTimeout(tick, delay);
  }
  function tick() {
    timer = null;
    if (opts.blocked() || hover || focus) {
      start();
      return;
    }
    set(true);
  }

  start();
  return {
    poke() { set(false); start(); },
    toggle() { if (hidden) { set(false); start(); } else { this.hide(); } },
    hide() {
      if (opts.blocked() || hover || focus) return;
      clear();
      set(true);
    },
    setHover(v: boolean) { hover = v; if (!v) start(); },
    setFocus(v: boolean) {
      focus = v;
      if (v) set(false);
      else start();
    },
    destroy() { clear(); },
  };
}
