import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { flushSync } from "svelte";
import PlayerBar from "./PlayerBar.svelte";
import { player } from "./player.svelte";

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

  it("speed button shows 1x and click goes to 1.25x", () => {
    player.setRate(1);
    renderBar();
    const rateBtn = btn("Playback speed");
    expect(rateBtn).not.toBeNull();
    expect(rateBtn!.textContent).toBe("1x");
    rateBtn!.click();
    flushSync();
    expect(btn("Playback speed")!.textContent).toBe("1.25x");
  });

  it("compact: prev/next shown, no speed button", () => {
    renderBar(true);
    expect(btn("Previous video")).not.toBeNull();
    expect(btn("Next video")).not.toBeNull();
    expect(btn("Playback speed")).toBeNull();
  });
});
