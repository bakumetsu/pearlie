import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createPlayer, type PlayerItem, type VideoLike } from "./player.svelte";
import type { Rect } from "./geometry.ts";

const item1: PlayerItem = { id: "1", title: "A", streamUrl: "", posterUrl: "", href: "" };
const item2: PlayerItem = { id: "2", title: "B", streamUrl: "", posterUrl: "", href: "" };
const rect: Rect = { x: 0, y: 0, w: 100, h: 50 };

const fake = (): VideoLike => ({
  play: vi.fn(() => Promise.resolve()),
  pause: vi.fn(),
  currentTime: 0,
  volume: 1,
  muted: false,
});

describe("createPlayer", () => {
  it("open sets stage and clears slot", () => {
    const p = createPlayer();
    const f = fake();
    p.attach(f);
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.open(item2);
    expect(p.mode).toBe("stage");
    expect(p.slot).toBeNull();
    expect(p.item?.id).toBe("2");
  });

  it("open same id keeps time and playing", () => {
    const p = createPlayer();
    p.open(item1);
    p.onPlaying();
    p.onTime(42, 100);
    p.open(item1);
    expect(p.mode).toBe("stage");
    expect(p.time).toBe(42);
    expect(p.duration).toBe(100);
    expect(p.playing).toBe(true);
  });

  it("open another id pauses old el and resets", () => {
    const p = createPlayer();
    const f = fake();
    p.attach(f);
    p.open(item1);
    p.onPlaying();
    p.onTime(30, 90);
    p.open(item2);
    expect(f.pause).toHaveBeenCalled();
    expect(p.item?.id).toBe("2");
    expect(p.time).toBe(0);
    expect(p.duration).toBe(0);
    expect(p.playing).toBe(false);
  });

  it("setSlot ignored for wrong id", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot("other", rect);
    expect(p.slot).toBeNull();
  });

  it("setSlot stores rect", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    expect(p.slot).toEqual(rect);
    expect(p.mode).toBe("stage");
  });

  it("releaseSlot while playing -> mini and item kept", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.onPlaying();
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("mini");
    expect(p.item?.id).toBe("1");
    expect(p.slot).toBeNull();
  });

  it("releaseSlot while paused -> hidden and item null", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("hidden");
    expect(p.item).toBeNull();
    expect(p.playing).toBe(false);
    expect(p.time).toBe(0);
    expect(p.duration).toBe(0);
  });

  it("releaseSlot with wrong id ignored", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.releaseSlot("other");
    expect(p.mode).toBe("stage");
    expect(p.slot).toEqual(rect);
    expect(p.item?.id).toBe("1");
  });

  it("close resets", () => {
    const p = createPlayer();
    const f = fake();
    p.attach(f);
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.onPlaying();
    p.onTime(10, 60);
    p.close();
    expect(f.pause).toHaveBeenCalled();
    expect(p.mode).toBe("hidden");
    expect(p.item).toBeNull();
    expect(p.playing).toBe(false);
    expect(p.time).toBe(0);
    expect(p.duration).toBe(0);
    expect(p.slot).toBeNull();
  });

  it("seek sets el.currentTime", () => {
    const p = createPlayer();
    const f = fake();
    p.attach(f);
    p.open(item1);
    p.seek(5.5);
    expect(f.currentTime).toBe(5.5);
    expect(p.time).toBe(5.5);
  });

  it("setVolume clamps and unmutes", () => {
    const p = createPlayer();
    const f = fake();
    p.attach(f);
    p.open(item1);
    p.setVolume(1.5);
    expect(p.volume).toBe(1);
    expect(p.muted).toBe(false);
    expect(f.volume).toBe(1);
    expect(f.muted).toBe(false);
    p.setVolume(-0.5);
    expect(p.volume).toBe(0);
    expect(f.volume).toBe(0);
  });

  it("onTime ignores non-finite duration", () => {
    const p = createPlayer();
    p.open(item1);
    p.onTime(3, NaN);
    expect(p.time).toBe(3);
    expect(p.duration).toBe(0);
    p.onTime(5, Infinity);
    expect(p.time).toBe(5);
    expect(p.duration).toBe(0);
  });

  it("play rejection leaves playing false", async () => {
    const p = createPlayer();
    const f = fake();
    f.play = vi.fn(() => Promise.reject(new Error("x")));
    p.attach(f);
    p.open(item1);
    p.onPlaying();
    p.play();
    await new Promise<void>((r) => setTimeout(r, 0));
    expect(p.playing).toBe(false);
  });

  it("source error walks the fallbacks, then marks failed", () => {
    const p = createPlayer();
    p.open({ ...item1, fallbacks: [{ url: "/a", mime: "video/mp4" }, { url: "/b", mime: "video/mp4" }] });
    expect(p.onSourceError()).toBe("/a");
    expect(p.failed).toBe(false);
    expect(p.onSourceError()).toBe("/b");
    expect(p.failed).toBe(false);
    expect(p.onSourceError()).toBeNull();
    expect(p.failed).toBe(true);
    p.open(item2);
    expect(p.failed).toBe(false);
  });
});

describe("createPlayer controls", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v); },
      removeItem: (k: string) => { store.delete(k); },
      clear: () => { store.clear(); },
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("skip +10 clamped at duration", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1 };
    p.attach(f);
    p.open(item1);
    p.onTime(90, 100);
    p.skip(10);
    expect(p.time).toBe(100);
    expect(f.currentTime).toBe(100);
  });

  it("skip -10 clamped at 0", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1 };
    p.attach(f);
    p.open(item1);
    p.onTime(5, 100);
    p.skip(-10);
    expect(p.time).toBe(0);
    expect(f.currentTime).toBe(0);
  });

  it("skip with duration 0 never goes below 0", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1 };
    p.attach(f);
    p.open(item1);
    p.onTime(0, 0);
    p.skip(-10);
    expect(p.time).toBe(0);
  });

  it("rate default 1", () => {
    const p = createPlayer();
    expect(p.rate).toBe(1);
  });

  it("setRate persists to localStorage and a new createPlayer re-reads it", () => {
    const p = createPlayer();
    p.setRate(1.5);
    expect(localStorage.getItem("pearlie.player.rate")).toBe("1.5");
    const p2 = createPlayer();
    expect(p2.rate).toBe(1.5);
  });

  it("invalid stored value falls back to 1", () => {
    localStorage.setItem("pearlie.player.rate", "99");
    const p = createPlayer();
    expect(p.rate).toBe(1);
  });

  it("setRate(3) ignored", () => {
    const p = createPlayer();
    p.setRate(3);
    expect(p.rate).toBe(1);
  });

  it("stepRate clamps at 0.5 and 2", () => {
    const p = createPlayer();
    p.setRate(0.5);
    p.stepRate(-1);
    expect(p.rate).toBe(0.5);
    p.setRate(2);
    p.stepRate(1);
    expect(p.rate).toBe(2);
  });

  it("rate applied to attached el", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1 };
    p.attach(f);
    p.setRate(1.5);
    expect(f.playbackRate).toBe(1.5);
  });

  it("rate kept after open(other item)", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1 };
    p.attach(f);
    p.setRate(2);
    p.open(item1);
    p.open(item2);
    expect(f.playbackRate).toBe(2);
  });

  it("nav null -> canNext/canPrev false", () => {
    const p = createPlayer();
    expect(p.canNext).toBe(false);
    expect(p.canPrev).toBe(false);
  });

  it("with a fake nav, next/prev call it and canNext reflects it", () => {
    const p = createPlayer();
    const nextSpy = vi.fn();
    const prevSpy = vi.fn();
    p.setNav({ next: nextSpy, prev: prevSpy, canNext: () => true, canPrev: () => false });
    p.next();
    p.prev();
    expect(nextSpy).toHaveBeenCalled();
    expect(prevSpy).toHaveBeenCalled();
    expect(p.canNext).toBe(true);
    expect(p.canPrev).toBe(false);
  });
});
