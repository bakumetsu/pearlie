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
    setFocus(v: boolean) { focus = v; if (!v) start(); },
    destroy() { clear(); },
  };
}
