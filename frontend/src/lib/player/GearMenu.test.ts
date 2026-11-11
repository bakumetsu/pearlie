import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import { flushSync, tick } from "svelte";
import GearMenu from "./GearMenu.svelte";
import src from "./GearMenu.svelte?raw";
import { player, RATES } from "./player.svelte";
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
  function row(name: string) {
    const items = document.querySelectorAll<HTMLElement>('[role^="menuitem"]');
    return Array.from(items).find((el) => el.textContent!.includes(name)) ?? null;
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

  it("focusOut to outside closes the menu", async () => {
    gear()!.click();
    flushSync();
    await tick();

    const apRow = row("Autoplay")!;
    apRow.focus();

    await fireEvent.focusOut(apRow, { relatedTarget: document.body, bubbles: true });
    flushSync();

    expect(pop()).toBeNull();
  });

  it("arrows navigate rows with wrap; Home/End jump", async () => {
    gear()!.click();
    flushSync();
    await tick();

    expect(document.activeElement).toBe(row("Autoplay")!);

    await fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(document.activeElement).toBe(row("Loop")!);

    await fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(document.activeElement).toBe(row("Speed")!);

    await fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(document.activeElement).toBe(row("Quality")!);

    await fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(document.activeElement).toBe(row("Autoplay")!);

    await fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(document.activeElement).toBe(row("Quality")!);

    await fireEvent.keyDown(window, { key: "End" });
    expect(document.activeElement).toBe(row("Quality")!);

    await fireEvent.keyDown(window, { key: "Home" });
    expect(document.activeElement).toBe(row("Autoplay")!);
  });

  it("keys do not leak to bubble listener while open; leak after close", () => {
    gear()!.click();
    flushSync();

    const spy = vi.fn();
    window.addEventListener("keydown", spy);

    const keys = ["j", "l", " ", "<", ">", "ArrowLeft"];
    for (const key of keys) {
      const before = spy.mock.calls.length;
      document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      expect(spy.mock.calls.length).toBe(before);
    }

    gear()!.click();
    flushSync();
    expect(pop()).toBeNull();

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "j", bubbles: true }));
    expect(spy).toHaveBeenCalledTimes(1);

    window.removeEventListener("keydown", spy);
  });

  it("reduced motion: prefers-reduced-motion rule disables transition and animation", () => {
    expect(src).toMatch(/prefers-reduced-motion:\s*reduce/);
    const after = src.slice(src.indexOf("prefers-reduced-motion"));
    expect(after).toContain("transition: none");
    expect(after).toContain("animation: none");
  });

  it("listeners removed on close", () => {
    const spy = vi.spyOn(window, "removeEventListener");

    gear()!.click();
    flushSync();
    expect(pop()).not.toBeNull();

    gear()!.click();
    flushSync();
    expect(pop()).toBeNull();

    expect(spy).toHaveBeenCalledWith("keydown", expect.any(Function), true);
    expect(spy).toHaveBeenCalledWith("pointerdown", expect.any(Function), true);

    spy.mockRestore();
  });

  it("main rows in order; Speed/Quality values; Quality absent without fallbacks", () => {
    gear()!.click();
    flushSync();

    const items = Array.from(
      document.querySelectorAll<HTMLElement>('[role^="menuitem"]')
    );
    const texts = items.map((el) => el.textContent!.trim());
    expect(texts[0]).toContain("Autoplay");
    expect(texts[1]).toContain("Loop");
    expect(texts[2]).toContain("Speed");
    expect(texts[3]).toContain("Quality");

    expect(row("Speed")!.querySelector(".value")!.textContent!.trim()).toBe("Normal");

    player.setRate(1.5);
    flushSync();
    expect(row("Speed")!.querySelector(".value")!.textContent!.trim()).toBe("1.5x");

    expect(row("Quality")!.querySelector(".value")!.textContent!.trim()).toBe("Direct");

    player.open({ ...item, id: "v4", fallbacks: [] });
    flushSync();
    expect(row("Quality")).toBeNull();

    player.setRate(1);
  });

  it("speed page: back row, RATES options, focus on current, pick 1.5x stays on main", async () => {
    const v = mockVideo();
    player.attach(v as never);

    gear()!.click();
    flushSync();

    await fireEvent.click(row("Speed")!);
    flushSync();
    await tick();

    const items = Array.from(
      document.querySelectorAll<HTMLElement>('[role^="menuitem"]')
    );
    expect(items[0].getAttribute("aria-label")).toBe("Back to settings");

    const opts = items.slice(1);
    expect(opts.length).toBe(RATES.length);
    RATES.forEach((r, i) => {
      expect(opts[i].textContent!.trim()).toBe(r + "x");
      expect(opts[i].getAttribute("role")).toBe("menuitemradio");
    });

    const oneIdx = (RATES as readonly number[]).indexOf(1);
    expect(document.activeElement).toBe(items[oneIdx + 1]);
    expect(items[oneIdx + 1].getAttribute("aria-checked")).toBe("true");

    await fireEvent.click(row("1.5x")!);
    flushSync();
    await tick();

    expect(player.rate).toBe(1.5);
    expect(v.playbackRate).toBe(1.5);
    expect(pop()).not.toBeNull();
    expect(document.activeElement).toBe(row("Speed")!);

    player.attach(null as never);
  });

  it("back row, ArrowLeft/Backspace, ArrowRight, Escape navigation", async () => {
    gear()!.click();
    flushSync();
    await tick();

    const speedRow = row("Speed")!;

    // ArrowRight on Speed row opens speed page
    speedRow.focus();
    await fireEvent.keyDown(speedRow, { key: "ArrowRight" });
    flushSync();
    await tick();
    expect(document.querySelector('[aria-label="Back to settings"]')).not.toBeNull();

    // ArrowLeft goes back to main, focus on Speed
    await fireEvent.keyDown(window, { key: "ArrowLeft" });
    flushSync();
    await tick();
    expect(document.activeElement).toBe(row("Speed")!);

    // ArrowRight opens speed again
    const sr1 = row("Speed")!;
    sr1.focus();
    await fireEvent.keyDown(sr1, { key: "ArrowRight" });
    flushSync();
    await tick();

    // Backspace goes back
    await fireEvent.keyDown(window, { key: "Backspace" });
    flushSync();
    await tick();
    expect(document.activeElement).toBe(row("Speed")!);

    // Open speed, Escape goes back (menu stays open)
    const sr2 = row("Speed")!;
    sr2.focus();
    await fireEvent.keyDown(sr2, { key: "ArrowRight" });
    flushSync();
    await tick();
    expect(pop()).not.toBeNull();

    await fireEvent.keyDown(window, { key: "Escape" });
    flushSync();
    await tick();
    expect(pop()).not.toBeNull();
    expect(document.activeElement).toBe(row("Speed")!);

    // Escape again closes and focuses gear
    await fireEvent.keyDown(window, { key: "Escape" });
    flushSync();
    expect(pop()).toBeNull();
    expect(document.activeElement).toBe(gear()!);
  });

  it("quality page lists Direct, 720p, 480p; Direct aria-checked true", async () => {
    gear()!.click();
    flushSync();

    await fireEvent.click(row("Quality")!);
    flushSync();

    expect(opt("Direct")).not.toBeNull();
    expect(opt("720p")).not.toBeNull();
    expect(opt("480p")).not.toBeNull();
    expect(opt("Direct")!.getAttribute("aria-checked")).toBe("true");
  });

  it("quality keeps position and play state", async () => {
    const v = mockVideo();
    player.attach(v as never);
    v.currentTime = 42;
    player.onPlaying();

    gear()!.click();
    flushSync();

    await fireEvent.click(row("Quality")!);
    flushSync();

    await fireEvent.click(opt("720p")!);
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

    gear()!.click();
    flushSync();

    await fireEvent.click(row("Quality")!);
    flushSync();

    await fireEvent.click(opt("Direct")!);
    flushSync();

    v.fire("loadedmetadata");
    flushSync();

    expect(v.play.mock.calls.length).toBe(playCountBefore);

    player.attach(null as never);
  });

  it("error after manual pick still falls back", async () => {
    gear()!.click();
    flushSync();

    await fireEvent.click(row("Quality")!);
    flushSync();

    await fireEvent.click(opt("720p")!);
    flushSync();

    expect(player.sourceIdx).toBe(0);

    const fallbackUrl = player.onSourceError();
    expect(fallbackUrl).toBe("/t480");
    expect(player.sourceIdx).toBe(1);
  });

  it("switches: Loop role/aria-checked, click toggles, Autoplay click, Space/Enter toggle once", async () => {
    gear()!.click();
    flushSync();

    const loopRow = row("Loop")!;
    expect(loopRow.getAttribute("role")).toBe("menuitemcheckbox");
    expect(loopRow.getAttribute("aria-checked")).toBe("false");

    await fireEvent.click(loopRow);
    flushSync();
    expect(player.loop).toBe(true);
    expect(loopRow.getAttribute("aria-checked")).toBe("true");
    expect(pop()).not.toBeNull();

    player.setLoop(false);
    flushSync();

    const apRow = row("Autoplay")!;
    expect(apRow.getAttribute("role")).toBe("menuitemcheckbox");

    await fireEvent.click(apRow);
    flushSync();
    expect(playerSettings.autoplay).toBe(true);
    expect(pop()).not.toBeNull();

    await playerSettings.setAutoplay(false);
    flushSync();

    // Space keydown toggles exactly once
    const loopRow2 = row("Loop")!;
    loopRow2.focus();
    await fireEvent.keyDown(loopRow2, { key: " " });
    flushSync();
    expect(player.loop).toBe(true);

    player.setLoop(false);
    flushSync();

    // Enter keydown toggles exactly once
    const loopRow3 = row("Loop")!;
    loopRow3.focus();
    await fireEvent.keyDown(loopRow3, { key: "Enter" });
    flushSync();
    expect(player.loop).toBe(true);
  });

  it("drag suppresses click after exceeding dead zone; dead-zone drag + click toggles once", async () => {
    HTMLElement.prototype.setPointerCapture = vi.fn();

    gear()!.click();
    flushSync();

    const loopRow = row("Loop")!;

    // Drag beyond dead zone: down 100, move 130 (dx=30>12 → moved), up 130 (dx=30>18 → apply)
    await fireEvent.pointerDown(loopRow, { clientX: 100, pointerId: 1 });
    await fireEvent.pointerMove(loopRow, { clientX: 130, pointerId: 1 });
    await fireEvent.pointerUp(loopRow, { clientX: 130, pointerId: 1 });
    flushSync();
    expect(player.loop).toBe(true);

    // Click after drag is suppressed
    await fireEvent.click(loopRow);
    flushSync();
    expect(player.loop).toBe(true);

    player.setLoop(false);
    flushSync();

    // Dead-zone drag: down 100, move 108 (dx=8, not >12), up 108
    await fireEvent.pointerDown(loopRow, { clientX: 100, pointerId: 1 });
    await fireEvent.pointerMove(loopRow, { clientX: 108, pointerId: 1 });
    await fireEvent.pointerUp(loopRow, { clientX: 108, pointerId: 1 });
    flushSync();
    expect(player.loop).toBe(false);

    // Click after dead-zone drag toggles once
    await fireEvent.click(loopRow);
    flushSync();
    expect(player.loop).toBe(true);
  });

  it("page resets to main when reopened", async () => {
    gear()!.click();
    flushSync();

    await fireEvent.click(row("Speed")!);
    flushSync();
    await tick();
    expect(document.querySelector('[aria-label="Back to settings"]')).not.toBeNull();

    gear()!.click();
    flushSync();
    expect(pop()).toBeNull();

    gear()!.click();
    flushSync();
    expect(row("Autoplay")).not.toBeNull();
    expect(row("Loop")).not.toBeNull();
    expect(row("Speed")).not.toBeNull();
    expect(document.querySelector('[aria-label="Back to settings"]')).toBeNull();
  });
});
