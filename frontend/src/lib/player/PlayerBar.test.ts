import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import PlayerBar from "./PlayerBar.svelte";
import { player } from "./player.svelte";
import barSource from "./PlayerBar.svelte?raw";

describe("PlayerBar controls: prev/next, skip, speed", () => {
  const item = { id: "v1", title: "t", streamUrl: "/s", posterUrl: "/p", href: "/item/videos/v1" };

  beforeEach(() => {
    player.open(item);
  });

  afterEach(() => {
    cleanup();
    player.setNav(null);
    player.close();
  });

  function renderBar(compact = false) {
    render(PlayerBar, { props: { compact } });
    flushSync();
  }

  function btn(label: string) {
    return document.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`);
  }

  it("prev disabled when canPrev false, next enabled when canNext true", () => {
    player.setNav({ next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => false });
    renderBar();
    const prev = btn("Previous video");
    const next = btn("Next video");
    expect(prev).not.toBeNull();
    expect(next).not.toBeNull();
    expect(prev!.disabled).toBe(true);
    expect(next!.disabled).toBe(false);
  });

  it("click next calls nav.next", () => {
    const nextFn = vi.fn();
    player.setNav({ next: nextFn, prev: vi.fn(), canNext: () => true, canPrev: () => true });
    renderBar();
    btn("Next video")!.click();
    expect(nextFn).toHaveBeenCalled();
  });

  it("double-chevron back calls nav.prev", () => {
    const prevFn = vi.fn();
    player.setNav({ next: vi.fn(), prev: prevFn, canNext: () => true, canPrev: () => true });
    renderBar();
    btn("Previous video")!.click();
    expect(prevFn).toHaveBeenCalled();
  });

  it("double-chevron forward calls nav.next", () => {
    const nextFn = vi.fn();
    player.setNav({ next: nextFn, prev: vi.fn(), canNext: () => true, canPrev: () => true });
    renderBar();
    btn("Next video")!.click();
    expect(nextFn).toHaveBeenCalled();
  });

  it("prev/next buttons disabled when nav is null", () => {
    player.setNav(null);
    renderBar();
    const prev = btn("Previous video");
    const next = btn("Next video");
    expect(prev).not.toBeNull();
    expect(next).not.toBeNull();
    expect(prev!.disabled).toBe(true);
    expect(next!.disabled).toBe(true);
  });

  it("no 1x speed button; gear button present", () => {
    renderBar();
    expect(btn("Playback speed")).toBeNull();
    expect(btn("Player settings")).not.toBeNull();
  });

  it("gear sits after mute and before fullscreen", () => {
    renderBar();
    const gear = btn("Player settings");
    const mute = btn("Mute");
    const fs = btn("Fullscreen");
    expect(gear).not.toBeNull();
    expect(mute).not.toBeNull();
    expect(fs).not.toBeNull();
    expect(mute!.compareDocumentPosition(gear!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(gear!.compareDocumentPosition(fs!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("skip buttons: labels, title, skip(-10)/skip(10)", async () => {
    player.onTime(50, 100);
    const spy = vi.spyOn(player, "skip");
    renderBar();
    const back = btn("Back 10 seconds")!;
    const fwd = btn("Forward 10 seconds")!;
    expect(back.getAttribute("title")).toBe("Back 10 seconds");
    expect(fwd.getAttribute("title")).toBe("Forward 10 seconds");
    expect(back.disabled).toBe(false);
    await fireEvent.click(back);
    await fireEvent.click(fwd);
    expect(spy).toHaveBeenNthCalledWith(1, -10);
    expect(spy).toHaveBeenNthCalledWith(2, 10);
    spy.mockRestore();
  });

  it("skip buttons disabled while duration is 0", () => {
    renderBar();
    expect(player.duration).toBe(0);
    expect(btn("Back 10 seconds")!.disabled).toBe(true);
    expect(btn("Forward 10 seconds")!.disabled).toBe(true);
  });

  it("skip buttons disabled when the player failed", () => {
    player.onTime(5, 100);
    player.onSourceError();
    expect(player.failed).toBe(true);
    renderBar();
    expect(btn("Back 10 seconds")!.disabled).toBe(true);
    expect(btn("Forward 10 seconds")!.disabled).toBe(true);
  });

  it("DOM order of the whole bar", () => {
    player.onTime(0, 100);
    renderBar();
    const els = Array.from(
      document.querySelectorAll<HTMLElement>(".bar button, .bar input, .bar .time"),
    );
    const key = (e: HTMLElement) => e.getAttribute("aria-label") ?? (e.classList.contains("time") ? "time" : "");
    const keys = els.map(key);
    const want = [
      "Previous video", "Back 10 seconds", "Play", "Forward 10 seconds", "Next video",
      "Seek", "time", "Mute", "Volume",
    ];
    expect(keys.slice(0, want.length)).toEqual(want);
    const tail = keys.slice(want.length);
    expect(tail[tail.length - 1]).toBe("Fullscreen");
    expect(tail[tail.length - 2]).toBe("Player settings");
  });

  it("bar-wrap is a size container without overflow or position", () => {
    renderBar();
    expect(document.querySelector(".bar-wrap > .bar")).not.toBeNull();
    const rule = barSource.match(/\.bar-wrap\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/container-type:\s*inline-size/);
    expect(rule).not.toMatch(/overflow/);
    expect(rule).not.toMatch(/position\s*:/);
    const bar = barSource.match(/\n\s*\.bar\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(bar).not.toMatch(/overflow/);
  });

  it("volume slider hidden by a container query below 680px", () => {
    expect(barSource).toMatch(/@container\s*\(max-width:\s*679px\)\s*\{\s*\.vol\s*\{\s*display:\s*none/);
  });

  it("no fixed width that overflows at 360/768/1280", () => {
    const widthRules = [...barSource.matchAll(/([^{}]+)\{([^}]*)\}/g)]
      .filter(([, , body]) => /(^|[\s;])(width|min-width)\s*:\s*\d+px/.test(body))
      .map(([, sel]) => sel.trim());
    // .btn 44px, .seek min 60px, .vol 64px (hidden below 680): 11 items fit 360 only because vol is hidden and seek shrinks
    expect(widthRules.sort()).toEqual([".btn", ".seek", ".vol"].sort());
    const seek = barSource.match(/\.seek\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(seek).toMatch(/flex:\s*1/);
    expect(seek).not.toMatch(/(^|[\s;])width\s*:/);
  });

  it("compact: prev/next shown, no speed button, no gear", () => {
    renderBar(true);
    expect(btn("Previous video")).not.toBeNull();
    expect(btn("Next video")).not.toBeNull();
    expect(btn("Playback speed")).toBeNull();
    expect(btn("Player settings")).toBeNull();
  });
});
