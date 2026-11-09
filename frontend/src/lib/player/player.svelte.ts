import { modeOnLeave, type Rect, type PlayerMode } from "./geometry";

export const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
const RATE_KEY = "pearlie.player.rate";
function loadRate(): number {
  try {
    const v = Number(localStorage.getItem(RATE_KEY));
    if ((RATES as readonly number[]).includes(v)) return v;
  } catch {}
  return 1;
}

export type PlayerItem = { id: string; title: string; streamUrl: string; posterUrl: string; href: string; fallbacks?: { url: string; mime: string }[] };
export interface VideoLike {
  play(): Promise<void>;
  pause(): void;
  currentTime: number;
  volume: number;
  muted: boolean;
  playbackRate?: number;
}

export type PlayerNav = { next(): void; prev(): void; canNext(): boolean; canPrev(): boolean };

export function createPlayer() {
  const state = $state({
    mode: "hidden" as PlayerMode,
    item: null as PlayerItem | null,
    playing: false,
    time: 0,
    duration: 0,
    volume: 1,
    muted: false,
    slot: null as Rect | null,
    failed: false,
    rate: loadRate(),
  });

  let el: VideoLike | null = null;
  let fallbackIdx = 0;
  let nav: PlayerNav | null = null;
  let autoplay = false;
  let navVersion = $state(0);

  function applyRate(): void {
    if (el !== null) el.playbackRate = state.rate;
  }

  return {
    get mode(): PlayerMode { return state.mode; },
    get item(): PlayerItem | null { return state.item; },
    get playing(): boolean { return state.playing; },
    get time(): number { return state.time; },
    get duration(): number { return state.duration; },
    get volume(): number { return state.volume; },
    get muted(): boolean { return state.muted; },
    get rate(): number { return state.rate; },
    get slot(): Rect | null { return state.slot; },
    get failed(): boolean { return state.failed; },

    attach(v: VideoLike | null): void {
      el = v;
      if (v !== null) {
        v.volume = state.volume;
        v.muted = state.muted;
        applyRate();
      }
    },

    open(item: PlayerItem): void {
      if (state.item?.id === item.id) {
        state.mode = "stage";
        return;
      }
      el?.pause();
      state.item = item;
      state.failed = false;
      fallbackIdx = 0;
      state.time = 0;
      state.duration = 0;
      state.playing = false;
      state.slot = null;
      state.mode = "stage";
      autoplay = false;
      applyRate();
    },

    swap(item: PlayerItem): void {
      if (state.item?.id === item.id) return;
      el?.pause();
      state.item = item;
      state.failed = false;
      fallbackIdx = 0;
      state.time = 0;
      state.duration = 0;
      state.playing = false;
      autoplay = true;
      applyRate();
    },

    consumeAutoplay(): boolean {
      const a = autoplay;
      autoplay = false;
      return a;
    },

    setSlot(id: string, rect: Rect | null): void {
      if (state.item?.id !== id) return;
      state.slot = rect;
      if (rect !== null) state.mode = "stage";
    },

    releaseSlot(id: string): void {
      if (state.item?.id !== id || state.mode !== "stage") return;
      state.slot = null;
      const next = modeOnLeave(state.playing);
      if (next === "hidden") {
        el?.pause();
        state.item = null;
        state.time = 0;
        state.duration = 0;
        state.playing = false;
        state.mode = "hidden";
      } else {
        state.mode = "mini";
      }
    },

    play(): void {
      el?.play().catch(() => {
        state.playing = false;
      });
    },

    pause(): void {
      el?.pause();
      state.playing = false;
    },

    toggle(): void {
      if (state.playing) {
        el?.pause();
        state.playing = false;
      } else {
        el?.play().catch(() => {
          state.playing = false;
        });
      }
    },

    seek(t: number): void {
      if (el !== null) el.currentTime = t;
      state.time = t;
    },

    setVolume(v: number): void {
      const clamped = Math.min(1, Math.max(0, v));
      state.volume = clamped;
      if (el !== null) el.volume = clamped;
      if (clamped > 0) {
        state.muted = false;
        if (el !== null) el.muted = false;
      }
    },

    toggleMute(): void {
      state.muted = !state.muted;
      if (el !== null) el.muted = state.muted;
    },

    reapplyRate(): void {
      applyRate();
    },

    setRate(r: number): void {
      if (!(RATES as readonly number[]).includes(r)) return;
      state.rate = r;
      applyRate();
      try {
        localStorage.setItem(RATE_KEY, String(r));
      } catch {}
    },

    stepRate(dir: 1 | -1): void {
      const i = (RATES as readonly number[]).indexOf(state.rate);
      const j = Math.min(RATES.length - 1, Math.max(0, i + dir));
      this.setRate(RATES[j]);
    },

    skip(delta: number): void {
      const max = state.duration > 0 ? state.duration : Infinity;
      const target = Math.min(max, Math.max(0, state.time + delta));
      this.seek(target);
    },

    setNav(n: PlayerNav | null): void {
      nav = n;
      navVersion++;
    },

    get canNext(): boolean { void navVersion; return nav?.canNext() ?? false; },
    get canPrev(): boolean { void navVersion; return nav?.canPrev() ?? false; },
    next(): void { nav?.next(); },
    prev(): void { nav?.prev(); },

    close(): void {
      el?.pause();
      state.item = null;
      state.time = 0;
      state.duration = 0;
      state.playing = false;
      state.slot = null;
      state.mode = "hidden";
      state.failed = false;
    },

    /** Next fallback url after a source error, or null (and failed) when all are used. */
    onSourceError(): string | null {
      const fb = state.item?.fallbacks ?? [];
      if (fallbackIdx < fb.length) {
        const url = fb[fallbackIdx].url;
        fallbackIdx += 1;
        return url;
      }
      state.failed = true;
      return null;
    },

    onTime(t: number, d: number): void {
      state.time = t;
      if (Number.isFinite(d)) state.duration = d;
    },

    onPlaying(): void {
      state.playing = true;
    },

    onPause(): void {
      state.playing = false;
    },

    onEnded(): void {
      state.playing = false;
    },
  };
}

export const player = createPlayer();
