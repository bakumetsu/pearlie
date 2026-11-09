import { modeOnLeave, type Rect, type PlayerMode } from "./geometry";

export type PlayerItem = { id: string; title: string; streamUrl: string; posterUrl: string; href: string; fallbacks?: { url: string; mime: string }[] };
export interface VideoLike {
  play(): Promise<void>;
  pause(): void;
  currentTime: number;
  volume: number;
  muted: boolean;
}

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
  });

  let el: VideoLike | null = null;

  return {
    get mode(): PlayerMode { return state.mode; },
    get item(): PlayerItem | null { return state.item; },
    get playing(): boolean { return state.playing; },
    get time(): number { return state.time; },
    get duration(): number { return state.duration; },
    get volume(): number { return state.volume; },
    get muted(): boolean { return state.muted; },
    get slot(): Rect | null { return state.slot; },

    attach(v: VideoLike | null): void {
      el = v;
      if (v !== null) {
        v.volume = state.volume;
        v.muted = state.muted;
      }
    },

    open(item: PlayerItem): void {
      if (state.item?.id === item.id) {
        state.mode = "stage";
        return;
      }
      el?.pause();
      state.item = item;
      state.time = 0;
      state.duration = 0;
      state.playing = false;
      state.slot = null;
      state.mode = "stage";
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

    close(): void {
      el?.pause();
      state.item = null;
      state.time = 0;
      state.duration = 0;
      state.playing = false;
      state.slot = null;
      state.mode = "hidden";
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
