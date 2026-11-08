import { describe, it, expect, vi } from "vitest";
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
});
