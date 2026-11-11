import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import GearMenu from "./GearMenu.svelte";
import { player } from "./player.svelte";
import { playerSettings } from "./playerSettings.svelte";

describe("GearMenu popover, sections, speed, loop, quality", () => {
  const item = {
    id: "v1",
    title: "t",
    streamUrl: "/direct",
    posterUrl: "/p",
    href: "/item/videos/v1",
    fallbacks: [
      { url: "/t720", mime: "video/mp4", label: "720p" },
      { url: "/t480", mime: "video/mp4", label: "480p" },
    ],
  };

  function gear() {
    return document.querySelector<HTMLButtonElement>('[aria-label="Player settings"][aria-haspopup]');
  }
  function pop() {
    return document.querySelector<HTMLDivElement>("div.pop");
  }
  function header(name: string) {
    const heads = document.querySelectorAll<HTMLButtonElement>("button.head");
    return Array.from(heads).find((h) => h.textContent!.includes(name)) ?? null;
  }
  function opt(text: string) {
    const opts = document.querySelectorAll<HTMLButtonElement>("button.opt");
    return Array.from(opts).find((o) => o.textContent!.trim() === text) ?? null;
  }

  function mockVideo() {
    const listeners: Record<string, (() => void)[]> = {};
    return {
      play: vi.fn(() => Promise.resolve()),
      pause: vi.fn(),
      currentTime: 0,
      volume: 1,
      muted: false,
      playbackRate: 1,
      loop: false,
      src: "/direct",
      load: vi.fn(),
      addEventListener: (t: string, cb: () => void) => {
        (listeners[t] ??= []).push(cb);
      },
      fire: (t: string) => (listeners[t] ?? []).splice(0).forEach((cb) => cb()),
    };
  }

  beforeEach(() => {
    player.setRate(1);
    player.open(item);
    render(GearMenu);
    flushSync();
  });

  afterEach(() => {
    cleanup();
    player.close();
  });

  it("popover closed initially; gear opens; gear again closes", () => {
    expect(pop()).toBeNull();
    gear()!.click();
    flushSync();
    expect(pop()).not.toBeNull();
    gear()!.click();
    flushSync();
    expect(pop()).toBeNull();
  });

  it("outside tap closes; pointerdown inside popover does not close", () => {
    gear()!.click();
    flushSync();
    expect(pop()).not.toBeNull();

    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    flushSync();
    expect(pop()).toBeNull();
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

    gear()!.click();
    flushSync();
    expect(pop()).not.toBeNull();

    pop()!.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    flushSync();
    expect(pop()).not.toBeNull();
  });

  it("outside tap does not toggle play", () => {
    gear()!.click();
    flushSync();

    const clickSpy = vi.fn();
    window.addEventListener("click", clickSpy);

    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    flushSync();

    expect(clickSpy).not.toHaveBeenCalled();
    window.removeEventListener("click", clickSpy);
  });

  it("Escape closes; bubble-phase keydown on window not called", () => {
    gear()!.click();
    flushSync();
    expect(pop()).not.toBeNull();

    const spy = vi.fn();
    window.addEventListener("keydown", spy);

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    flushSync();

    expect(pop()).toBeNull();
    expect(spy).not.toHaveBeenCalled();
    window.removeEventListener("keydown", spy);
  });

  it("Speed expanded by default; header click collapses/expands; Quality independent", () => {
    gear()!.click();
    flushSync();

    // Speed expanded by default
    expect(header("Speed")!.getAttribute("aria-expanded")).toBe("true");
    expect(opt("1.25x")).not.toBeNull();

    // Collapse Speed
    header("Speed")!.click();
    flushSync();
    expect(opt("1.25x")).toBeNull();

    // Expand Speed again
    header("Speed")!.click();
    flushSync();
    expect(opt("1.25x")).not.toBeNull();

    // Quality header expanded=false initially
    expect(header("Quality")!.getAttribute("aria-expanded")).toBe("false");

    // Expanding Quality does not collapse Speed
    header("Quality")!.click();
    flushSync();
    expect(header("Quality")!.getAttribute("aria-expanded")).toBe("true");
    expect(header("Speed")!.getAttribute("aria-expanded")).toBe("true");
  });

  it("speed: picking 1.5x sets player.rate and video playbackRate, closes; aria-pressed correct on reopen", () => {
    const v = mockVideo();
    player.attach(v as never);

    gear()!.click();
    flushSync();

    opt("1.5x")!.click();
    flushSync();

    expect(player.rate).toBe(1.5);
    expect(v.playbackRate).toBe(1.5);
    expect(pop()).toBeNull();

    // Reopen and verify aria-pressed
    gear()!.click();
    flushSync();
    expect(opt("1.5x")!.getAttribute("aria-pressed")).toBe("true");
    expect(opt("1x")!.getAttribute("aria-pressed")).toBe("false");
    expect(opt("1.25x")!.getAttribute("aria-pressed")).toBe("false");

    player.attach(null as never);
  });

  it("loop: On sets player.loop and video.loop, closes; item change resets", () => {
    const v = mockVideo();
    player.attach(v as never);

    gear()!.click();
    flushSync();

    header("Loop")!.click();
    flushSync();

    opt("On")!.click();
    flushSync();

    expect(player.loop).toBe(true);
    expect(v.loop).toBe(true);
    expect(pop()).toBeNull();

    // Item change resets loop and sourceIdx
    player.open({ ...item, id: "v2" });
    flushSync();

    expect(player.loop).toBe(false);
    expect(player.sourceIdx).toBe(-1);

    player.attach(null as never);
  });

  it("quality lists Direct, 720p, 480p; Direct pressed; no fallbacks shows only Direct", () => {
    gear()!.click();
    flushSync();

    header("Quality")!.click();
    flushSync();

    expect(opt("Direct")).not.toBeNull();
    expect(opt("720p")).not.toBeNull();
    expect(opt("480p")).not.toBeNull();
    expect(opt("Direct")!.getAttribute("aria-pressed")).toBe("true");

    // Item with no fallbacks
    player.open({
      id: "v3",
      title: "t",
      streamUrl: "/direct",
      posterUrl: "/p",
      href: "/item/videos/v1",
      fallbacks: [],
    });
    flushSync();

    const opts = document.querySelectorAll<HTMLButtonElement>("button.opt");
    const qualityOpts = Array.from(opts).filter(
      (o) => ["Direct", "720p", "480p"].includes(o.textContent!.trim())
    );
    expect(qualityOpts.length).toBe(1);
    expect(qualityOpts[0].textContent!.trim()).toBe("Direct");
    expect(qualityOpts[0].getAttribute("aria-pressed")).toBe("true");
  });

  it("quality keeps position and play state", () => {
    const v = mockVideo();
    player.attach(v as never);
    v.currentTime = 42;
    player.onPlaying();

    gear()!.click();
    flushSync();
    header("Quality")!.click();
    flushSync();

    opt("720p")!.click();
    flushSync();

    expect(v.src).toBe("/t720");
    expect(v.load).toHaveBeenCalled();

    v.fire("loadedmetadata");
    flushSync();

    expect(v.currentTime).toBe(42);
    expect(v.play).toHaveBeenCalled();
    expect(player.sourceIdx).toBe(0);

    // Not playing: switch back to Direct, play not called again
    player.onPause();

    const playCountBefore = v.play.mock.calls.length;

    gear()!.click();
    flushSync();

    opt("Direct")!.click();
    flushSync();

    v.fire("loadedmetadata");
    flushSync();

    expect(v.play.mock.calls.length).toBe(playCountBefore);

    player.attach(null as never);
  });

  it("error after manual pick still falls back", () => {
    gear()!.click();
    flushSync();
    header("Quality")!.click();
    flushSync();

    opt("720p")!.click();
    flushSync();

    expect(player.sourceIdx).toBe(0);

    const fallbackUrl = player.onSourceError();
    expect(fallbackUrl).toBe("/t480");
    expect(player.sourceIdx).toBe(1);
  });

  it("autoplay: On sets the store and closes the menu", async () => {
    gear()!.click();
    flushSync();

    await fireEvent.click(header("Autoplay")!);
    flushSync();
    await fireEvent.click(opt("On")!);

    expect(playerSettings.autoplay).toBe(true);
    expect(pop()).toBeNull();

    await playerSettings.setAutoplay(false);
  });

  it("autoplay row shows Off as current by default", async () => {
    gear()!.click();
    flushSync();

    await fireEvent.click(header("Autoplay")!);
    flushSync();

    expect(opt("Off")!.getAttribute("aria-pressed")).toBe("true");
  });
});
