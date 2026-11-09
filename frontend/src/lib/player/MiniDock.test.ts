import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { flushSync } from "svelte";
import MiniDock from "./MiniDock.svelte";
import { player } from "./player.svelte";

vi.mock("../ctx", () => ({
  getRouter: () => ({ navigate: vi.fn() }),
}));

describe("MiniDock controls: prev/next only", () => {
  const item = { id: "v1", title: "t", streamUrl: "/s", posterUrl: "/p", href: "/item/videos/v1" };

  beforeEach(() => {
    player.open(item);
    player.onPlaying();
    player.setSlot("v1", { x: 0, y: 0, w: 100, h: 100 });
    player.releaseSlot("v1");
  });

  afterEach(() => {
    cleanup();
    player.setNav(null);
    player.close();
  });

  function renderDock() {
    render(MiniDock);
    flushSync();
  }

  function btn(label: string) {
    return document.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`);
  }

  it("prev/next buttons render and call nav.prev / nav.next", () => {
    const prevFn = vi.fn();
    const nextFn = vi.fn();
    player.setNav({ next: nextFn, prev: prevFn, canNext: () => true, canPrev: () => true });
    renderDock();
    const prev = btn("Previous video");
    const next = btn("Next video");
    expect(prev).not.toBeNull();
    expect(next).not.toBeNull();
    prev!.click();
    next!.click();
    expect(prevFn).toHaveBeenCalled();
    expect(nextFn).toHaveBeenCalled();
  });

  it("no skip or speed buttons", () => {
    player.setNav({ next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => true });
    renderDock();
    expect(btn("Close player")).not.toBeNull();
    expect(btn("Back 10 seconds")).toBeNull();
    expect(btn("Forward 10 seconds")).toBeNull();
    expect(btn("Playback speed")).toBeNull();
  });

  it("prev/next buttons disabled when nav is null", () => {
    player.setNav(null);
    renderDock();
    expect(btn("Close player")).not.toBeNull();
    const prev = btn("Previous video");
    const next = btn("Next video");
    expect(prev).not.toBeNull();
    expect(next).not.toBeNull();
    expect(prev!.disabled).toBe(true);
    expect(next!.disabled).toBe(true);
  });

  it("prev disabled when canPrev false", () => {
    player.setNav({ next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => false });
    renderDock();
    const prev = btn("Previous video");
    expect(prev).not.toBeNull();
    expect(prev!.disabled).toBe(true);
  });
});
