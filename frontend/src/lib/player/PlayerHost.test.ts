import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import PlayerHost from "./PlayerHost.svelte";
import { player } from "./player.svelte";

class FakeRO {
  observe() {}
  disconnect() {}
}

const item = { id: "v1", title: "t", streamUrl: "/s", posterUrl: "/api/stash/scenes/1/poster", href: "/item/videos/v1" };

describe("PlayerHost mini dock", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    player.open(item);
    player.onPlaying();
    player.setSlot("v1", { x: 10, y: 20, w: 300, h: 200 });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    player.close();
  });

  const video = () => document.querySelector<HTMLVideoElement>("video[data-player]");

  // jsdom drops the video's whole style string, so record what the component assigns
  function captureStyles(): string[] {
    const seen: string[] = [];
    const orig = Object.getOwnPropertyDescriptor(CSSStyleDeclaration.prototype, "cssText")!;
    vi.spyOn(CSSStyleDeclaration.prototype, "cssText", "set").mockImplementation(function (this: CSSStyleDeclaration, v: string) {
      seen.push(v);
      orig.set!.call(this, v);
    });
    return seen;
  }

  it("mini: video shows the poster above the dock and is not revealed", () => {
    player.releaseSlot("v1");
    expect(player.mode).toBe("mini");
    const seen = captureStyles();
    render(PlayerHost);
    flushSync();
    expect(video()?.getAttribute("poster")).toBe("/api/stash/scenes/1/poster");
    expect(seen.join("|")).toMatch(/z-index:\s*22\b/);
    expect(video()?.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("stage: video keeps z-index 20", () => {
    const seen = captureStyles();
    render(PlayerHost);
    flushSync();
    expect(seen.join("|")).toMatch(/z-index:\s*20\b/);
    expect(seen.join("|")).not.toMatch(/z-index:\s*22\b/);
  });
});

describe("PlayerHost rate", () => {
  let loadSpy: MockInstance;
  let playSpy: MockInstance;

  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    loadSpy = vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
    player.open(item);
    player.onPlaying();
    player.setSlot("v1", { x: 10, y: 20, w: 300, h: 200 });
    player.setRate(1);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    player.close();
  });

  const video = () => document.querySelector<HTMLVideoElement>("video[data-player]");

  it("speed change keeps playing, no reload", () => {
    render(PlayerHost);
    flushSync();
    const v = video()!;
    Object.defineProperty(v, "currentTime", { value: 12, writable: true, configurable: true });
    const loadCount = loadSpy.mock.calls.length;
    const playCount = playSpy.mock.calls.length;
    player.setRate(1.5);
    flushSync();
    expect(loadSpy.mock.calls.length).toBe(loadCount);
    expect(playSpy.mock.calls.length).toBe(playCount);
    expect(v.playbackRate).toBe(1.5);
    expect(v.currentTime).toBe(12);
    expect(player.playing).toBe(true);
  });

  it("rate survives an item change", () => {
    render(PlayerHost);
    flushSync();
    player.setRate(1.5);
    flushSync();
    const loadCount = loadSpy.mock.calls.length;
    player.open({ ...item, id: "v2", streamUrl: "/s2" });
    flushSync();
    expect(loadSpy.mock.calls.length).toBe(loadCount + 1);
    expect(video()!.playbackRate).toBe(1.5);
    expect(video()!.defaultPlaybackRate).toBe(1.5);
  });
});

describe("PlayerHost fullscreen", () => {
  type FsDoc = { exitFullscreen?: unknown };
  type FsEl = { requestFullscreen?: unknown; webkitRequestFullscreen?: unknown };

  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    player.open(item);
    player.onPlaying();
    player.setSlot("v1", { x: 10, y: 20, w: 300, h: 200 });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    player.close();
    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: null });
    delete (document as unknown as FsDoc).exitFullscreen;
  });

  function setFs(el: Element | null) {
    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: el });
    document.dispatchEvent(new Event("fullscreenchange"));
    flushSync();
  }

  function setupFsMocks() {
    const root = document.querySelector("[data-player-root]")!;
    const video = document.querySelector("video[data-player]")!;
    root.requestFullscreen = vi.fn(() => { setFs(root); return Promise.resolve(); });
    video.requestFullscreen = vi.fn(() => Promise.resolve());
    (document as unknown as FsDoc).exitFullscreen = vi.fn(() => { setFs(null); return Promise.resolve(); });
    return { root, video };
  }

  it("click Fullscreen enters root fullscreen, not video", async () => {
    render(PlayerHost);
    flushSync();
    const { root, video } = setupFsMocks();
    const btn = document.querySelector('[aria-label="Fullscreen"]')!;
    await fireEvent.click(btn);
    expect(root.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(video.requestFullscreen).not.toHaveBeenCalled();
  });

  it("bar stays mounted and button label changes in fullscreen", async () => {
    render(PlayerHost);
    flushSync();
    setupFsMocks();
    const btn = document.querySelector('[aria-label="Fullscreen"]')!;
    await fireEvent.click(btn);
    expect(document.querySelector('[aria-label="Player controls"]')).not.toBeNull();
    expect(document.querySelector('[aria-label="Exit fullscreen"]')).not.toBeNull();
  });

  it("Esc exits fullscreen, label reverts, bar still mounted", async () => {
    render(PlayerHost);
    flushSync();
    setupFsMocks();
    const btn = document.querySelector('[aria-label="Fullscreen"]')!;
    await fireEvent.click(btn);
    // simulate Esc key
    setFs(null);
    expect(document.querySelector('[aria-label="Fullscreen"]')).not.toBeNull();
    expect(document.querySelector('[aria-label="Player controls"]')).not.toBeNull();
  });

  it("click Exit fullscreen calls document.exitFullscreen", async () => {
    render(PlayerHost);
    flushSync();
    setupFsMocks();
    const btn = document.querySelector('[aria-label="Fullscreen"]')!;
    await fireEvent.click(btn);
    const exitBtn = document.querySelector('[aria-label="Exit fullscreen"]')!;
    await fireEvent.click(exitBtn);
    expect(document.exitFullscreen).toHaveBeenCalledTimes(1);
  });

  it("falls back to video.requestFullscreen when root does not support it", async () => {
    render(PlayerHost);
    flushSync();
    const root = document.querySelector("[data-player-root]")!;
    const video = document.querySelector("video[data-player]")!;
    (root as unknown as FsEl).requestFullscreen = undefined;
    (root as unknown as FsEl).webkitRequestFullscreen = undefined;
    video.requestFullscreen = vi.fn(() => Promise.resolve());
    (document as unknown as FsDoc).exitFullscreen = vi.fn(() => { setFs(null); return Promise.resolve(); });
    const btn = document.querySelector('[aria-label="Fullscreen"]')!;
    await fireEvent.click(btn);
    expect(video.requestFullscreen).toHaveBeenCalledTimes(1);
  });

  it("unmount while fullscreen calls document.exitFullscreen", async () => {
    render(PlayerHost);
    flushSync();
    setupFsMocks();
    const btn = document.querySelector('[aria-label="Fullscreen"]')!;
    await fireEvent.click(btn);
    cleanup();
    expect(document.exitFullscreen).toHaveBeenCalledTimes(1);
  });
});
