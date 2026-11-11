import { modeOnLeave, type Rect, type PlayerMode } from "./geometry";
import { playerSettings } from "./playerSettings.svelte";

export const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;

export type PlayerItem = { id: string; title: string; streamUrl: string; posterUrl: string; href: string; fallbacks?: { url: string; mime: string; label?: string }[] };
export interface VideoLike {
  play(): Promise<void>;
  pause(): void;
  currentTime: number;
  volume: number;
  muted: boolean;
  playbackRate?: number;
  defaultPlaybackRate?: number;
  loop?: boolean;
  src?: string;
  load?(): void;
  addEventListener?(type: string, cb: () => void, opts?: { once?: boolean }): void;
}

export type PlayerNav = { next(): void; prev(): void; canNext(): boolean; canPrev(): boolean };

export function createPlayer(isAutoplay: () => boolean = () => playerSettings.autoplay) {
  const state = $state({
    mode: "hidden" as PlayerMode,
    item: null as PlayerItem | null,
    playing: false,
    ended: false,
    time: 0,
    duration: 0,
    volume: 1,
    muted: false,
    slot: null as Rect | null,
    failed: false,
    rate: 1,
    loop: false,
    sourceIdx: -1,
  });

  let el: VideoLike | null = null;
  let fallbackIdx = 0;
  let nav: PlayerNav | null = null;
  let playOnLoad = false;
  let navVersion = $state(0);

  function applyRate(): void {
    if (el !== null) {
      el.playbackRate = state.rate;
      el.defaultPlaybackRate = state.rate;
    }
  }

  function applyLoop(): void {
    if (el !== null) el.loop = state.loop;
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
    get loop(): boolean { return state.loop; },
    get sourceIdx(): number { return state.sourceIdx; },
    get slot(): Rect | null { return state.slot; },
    get failed(): boolean { return state.failed; },

    attach(v: VideoLike | null): void {
      el = v;
      if (v !== null) {
        v.volume = state.volume;
        v.muted = state.muted;
        applyRate();
        applyLoop();
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
      state.ended = false;
      state.slot = null;
      state.mode = "stage";
      state.loop = false;
      state.sourceIdx = -1;
      playOnLoad = isAutoplay();
      applyRate();
      applyLoop();
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
      state.ended = false;
      state.loop = false;
      state.sourceIdx = -1;
      playOnLoad = true;
      applyRate();
      applyLoop();
    },

    consumePlayOnLoad(): boolean {
      const a = playOnLoad;
      playOnLoad = false;
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
      const next = modeOnLeave(state.ended);
      if (next === "hidden") {
        el?.pause();
        state.item = null;
        state.time = 0;
        state.duration = 0;
        state.playing = false;
        state.ended = false;
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
      state.ended = false;
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

    setLoop(on: boolean): void {
      state.loop = on;
      applyLoop();
    },

    playSource(url: string, keep: boolean): void {
      if (el === null || el.src === undefined) return;
      const v = el;
      const t = v.currentTime;
      const wasPlaying = state.playing;
      v.src = url;
      v.load?.();
      applyRate();
      if (keep) {
        v.addEventListener?.("loadedmetadata", () => {
          v.currentTime = t;
          if (wasPlaying) v.play().catch(() => { state.playing = false; });
        }, { once: true });
      } else if (wasPlaying) {
        void v.play();
      }
    },

    setQuality(i: number): void {
      const item = state.item;
      if (item === null) return;
      const fb = item.fallbacks ?? [];
      if (i < -1 || i >= fb.length) return;
      if (i === state.sourceIdx && !state.failed) return;
      const url = i === -1 ? item.streamUrl : fb[i].url;
      state.sourceIdx = i;
      state.failed = false;
      fallbackIdx = i + 1;
      this.playSource(url, true);
    },

    reapplyRate(): void {
      applyRate();
    },

    setRate(r: number): void {
      if (!(RATES as readonly number[]).includes(r)) return;
      state.rate = r;
      applyRate();
      this.onRateChange?.(r);
    },

    /** Called after setRate() so the options store can save the change. */
    onRateChange: null as ((r: number) => void) | null,

    /** Silent: applies a rate loaded from the server, without saving it back. */
    loadRate(r: number): void {
      if (!(RATES as readonly number[]).includes(r)) return;
      state.rate = r;
      applyRate();
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
      state.ended = false;
      state.slot = null;
      state.mode = "hidden";
      state.failed = false;
      state.loop = false;
      state.sourceIdx = -1;
    },

    /** Next fallback url after a source error, or null (and failed) when all are used. */
    onSourceError(): string | null {
      const fb = state.item?.fallbacks ?? [];
      if (fallbackIdx < fb.length) {
        state.sourceIdx = fallbackIdx;
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
      state.ended = false;
    },

    onPause(): void {
      state.playing = false;
    },

    onEnded(): void {
      const already = state.ended;
      state.playing = false;
      state.ended = true;
      if (already) return;
      if (isAutoplay() && !state.loop && nav?.canNext()) {
        nav.next();
        return;
      }
      if (state.mode === "mini") this.close();
    },
  };
}

export const player = createPlayer();
