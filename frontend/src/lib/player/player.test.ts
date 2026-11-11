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

  it("releaseSlot while paused -> mini, item kept", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("mini");
    expect(p.item).toEqual(item1);
    expect(p.playing).toBe(false);
  });

  it("releaseSlot after ended -> hidden and item null", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.onEnded();
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("hidden");
    expect(p.item).toBeNull();
  });

  it("onEnded in mini closes the player", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("mini");
    p.onEnded();
    expect(p.mode).toBe("hidden");
    expect(p.item).toBeNull();
  });

  it("onEnded in stage keeps the stage", () => {
    const p = createPlayer();
    p.open(item1);
    p.setSlot(item1.id, rect);
    p.onEnded();
    expect(p.mode).toBe("stage");
    expect(p.item).toEqual(item1);
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

  it("setQuality after all sources failed clears failed and plays the chosen source", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1, src: "", load: vi.fn() };
    p.attach(f);
    p.open({ ...item1, streamUrl: "/direct", fallbacks: [{ url: "/a", mime: "video/mp4" }] });
    expect(p.onSourceError()).toBe("/a");
    expect(p.onSourceError()).toBeNull();
    expect(p.failed).toBe(true);
    p.setQuality(-1);
    expect(p.failed).toBe(false);
    expect(f.src).toBe("/direct");
    expect(f.load).toHaveBeenCalled();
  });

  it("quality switch keeps the rate", () => {
    const p = createPlayer();
    const f = { ...fake(), playbackRate: 1, src: "", load: vi.fn() };
    p.attach(f);
    p.open({ ...item1, streamUrl: "/direct", fallbacks: [{ url: "/a", mime: "video/mp4" }] });
    p.setRate(1.5);
    p.setQuality(0);
    expect(f.playbackRate).toBe(1.5);
    expect(f.defaultPlaybackRate).toBe(1.5);
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

describe("createPlayer swap", () => {
  function toMini(p: ReturnType<typeof createPlayer>): void {
    p.open(item1);
    p.onPlaying();
    p.setSlot(item1.id, rect);
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("mini");
  }

  it("swap in mini mode keeps mode and slot, changes item, resets state", () => {
    const p = createPlayer();
    const f = fake();
    p.attach(f);
    toMini(p);
    p.swap(item2);
    expect(p.mode).toBe("mini");
    expect(p.slot).toBeNull();
    expect(p.item?.id).toBe("2");
    expect(p.time).toBe(0);
    expect(p.duration).toBe(0);
    expect(p.playing).toBe(false);
    expect(f.pause).toHaveBeenCalled();
  });

  it("consumePlayOnLoad returns true once then false", () => {
    const p = createPlayer();
    toMini(p);
    p.swap(item2);
    expect(p.consumePlayOnLoad()).toBe(true);
    expect(p.consumePlayOnLoad()).toBe(false);
  });

  it("swap with same id is a no-op", () => {
    const p = createPlayer();
    toMini(p);
    p.swap(item1);
    expect(p.item?.id).toBe("1");
    expect(p.consumePlayOnLoad()).toBe(false);
  });

  it("open after swap resets playOnLoad", () => {
    const p = createPlayer();
    toMini(p);
    p.swap(item2);
    expect(p.consumePlayOnLoad()).toBe(true);
    p.open(item1);
    expect(p.consumePlayOnLoad()).toBe(false);
  });
});

describe("autoplay setting", () => {
  const nav = (canNext: boolean) => ({ next: vi.fn(), prev: vi.fn(), canNext: () => canNext, canPrev: () => false });

  function toMini(p: ReturnType<typeof createPlayer>): void {
    p.open(item1);
    p.onPlaying();
    p.setSlot(item1.id, rect);
    p.releaseSlot(item1.id);
    expect(p.mode).toBe("mini");
  }

  it("ended with autoplay on and canNext true calls next() once in stage mode", () => {
    const on = true;
    const p = createPlayer(() => on);
    const n = nav(true);
    p.open(item1);
    p.setNav(n);
    p.onEnded();
    expect(n.next).toHaveBeenCalledTimes(1);
  });

  it("ended fired twice calls next() only once", () => {
    const on = true;
    const p = createPlayer(() => on);
    const n = nav(true);
    p.open(item1);
    p.setNav(n);
    p.onEnded();
    p.onEnded();
    expect(n.next).toHaveBeenCalledTimes(1);
  });

  it("loop on does not call next()", () => {
    const on = true;
    const p = createPlayer(() => on);
    const n = nav(true);
    p.open(item1);
    p.setLoop(true);
    p.setNav(n);
    p.onEnded();
    expect(n.next).not.toHaveBeenCalled();
  });

  it("canNext false in mini mode does not call next() and closes the player", () => {
    const on = true;
    const p = createPlayer(() => on);
    const n = nav(false);
    toMini(p);
    p.setNav(n);
    p.onEnded();
    expect(n.next).not.toHaveBeenCalled();
    expect(p.mode).toBe("hidden");
    expect(p.item).toBeNull();
  });

  it("autoplay off does not call next()", () => {
    const on = false;
    const p = createPlayer(() => on);
    const n = nav(true);
    p.open(item1);
    p.setNav(n);
    p.onEnded();
    expect(n.next).not.toHaveBeenCalled();
  });

  it("mini with autoplay on and canNext true: next() called and player not closed", () => {
    const on = true;
    const p = createPlayer(() => on);
    const n = nav(true);
    toMini(p);
    p.setNav(n);
    p.onEnded();
    expect(n.next).toHaveBeenCalledTimes(1);
    expect(p.item?.id).toBe("1");
    expect(p.mode).toBe("mini");
  });

  it("open with autoplay on gives consumePlayOnLoad true; off gives false", () => {
    const on = true;
    const p = createPlayer(() => on);
    p.open(item1);
    expect(p.consumePlayOnLoad()).toBe(true);
    const on2 = false;
    const p2 = createPlayer(() => on2);
    p2.open(item1);
    expect(p2.consumePlayOnLoad()).toBe(false);
  });

  it("swap in mini plays regardless of autoplay setting", () => {
    const on = false;
    const p = createPlayer(() => on);
    toMini(p);
    p.swap(item2);
    expect(p.consumePlayOnLoad()).toBe(true);
  });

  it("createPlayer reads the autoplay callback at call time, not creation time", () => {
    let on = true;
    const p = createPlayer(() => on);
    p.open(item1);
    expect(p.consumePlayOnLoad()).toBe(true);
    on = false;
    p.open(item2);
    expect(p.consumePlayOnLoad()).toBe(false);
  });
});
