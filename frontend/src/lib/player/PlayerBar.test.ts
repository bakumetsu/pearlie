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

  it("skip back 10s clamps at 0", () => {
    player.seek(5);
    renderBar();
    btn("Back 10 seconds")!.click();
    expect(player.time).toBe(0);
  });

  it("skip forward 10s from 30", () => {
    player.seek(30);
    renderBar();
    btn("Forward 10 seconds")!.click();
    expect(player.time).toBe(40);
  });

  it("no prev/next buttons when nav is null", () => {
    player.setNav(null);
    renderBar();
    expect(btn("Previous video")).toBeNull();
    expect(btn("Next video")).toBeNull();
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

  it("compact: no skip or speed buttons", () => {
    renderBar(true);
    expect(btn("Back 10 seconds")).toBeNull();
    expect(btn("Forward 10 seconds")).toBeNull();
    expect(btn("Playback speed")).toBeNull();
  });
});
