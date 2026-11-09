import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { flushSync } from "svelte";
import PlayerHost from "./PlayerHost.svelte";
import { player } from "./player.svelte";

class FakeRO {
  observe() {}
  disconnect() {}
}

const item = {
  id: "v1",
  title: "t",
  streamUrl: "/s",
  posterUrl: "/api/stash/scenes/1/poster",
  href: "/item/videos/v1",
};

function pressKey(
  key: string,
  opts: { shiftKey?: boolean; ctrlKey?: boolean; target?: HTMLElement } = {},
) {
  const target = opts.target ?? document.body;
  const e = new KeyboardEvent("keydown", {
    key,
    shiftKey: opts.shiftKey ?? false,
    ctrlKey: opts.ctrlKey ?? false,
    bubbles: true,
  });
  target.dispatchEvent(e);
}

describe("PlayerHost keyboard shortcuts", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    player.open(item);
    player.onPlaying();
    player.setSlot("v1", { x: 10, y: 20, w: 300, h: 200 });
    player.setRate(1);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    player.close();
    player.setNav(null);
  });

  it("j skips back 10 seconds", () => {
    render(PlayerHost);
    flushSync();
    player.seek(30);
    pressKey("j");
    expect(player.time).toBe(20);
  });

  it("l skips forward 10 seconds", () => {
    render(PlayerHost);
    flushSync();
    player.seek(30);
    pressKey("l");
    expect(player.time).toBe(40);
  });

  it("Shift+j (J) skips back 10 seconds", () => {
    render(PlayerHost);
    flushSync();
    player.seek(30);
    pressKey("J", { shiftKey: true });
    expect(player.time).toBe(20);
  });

  it("Shift+l (L) skips forward 10 seconds", () => {
    render(PlayerHost);
    flushSync();
    player.seek(30);
    pressKey("L", { shiftKey: true });
    expect(player.time).toBe(40);
  });

  it("> raises rate to next step", () => {
    render(PlayerHost);
    flushSync();
    pressKey(">");
    expect(player.rate).toBe(1.25);
  });

  it("< lowers rate to previous step", () => {
    render(PlayerHost);
    flushSync();
    pressKey("<");
    expect(player.rate).toBe(0.75);
  });

  it("Shift+N calls nav.next", () => {
    const nav = { next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => true };
    player.setNav(nav);
    render(PlayerHost);
    flushSync();
    pressKey("N", { shiftKey: true });
    expect(nav.next).toHaveBeenCalled();
  });

  it("Shift+P calls nav.prev", () => {
    const nav = { next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => true };
    player.setNav(nav);
    render(PlayerHost);
    flushSync();
    pressKey("P", { shiftKey: true });
    expect(nav.prev).toHaveBeenCalled();
  });

  it("lowercase n does nothing", () => {
    const nav = { next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => true };
    player.setNav(nav);
    render(PlayerHost);
    flushSync();
    pressKey("n");
    expect(nav.next).not.toHaveBeenCalled();
  });

  it("lowercase p does nothing", () => {
    const nav = { next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => true };
    player.setNav(nav);
    render(PlayerHost);
    flushSync();
    pressKey("p");
    expect(nav.prev).not.toHaveBeenCalled();
  });

  it("keydown from INPUT target is ignored", () => {
    render(PlayerHost);
    flushSync();
    const input = document.createElement("input");
    document.body.appendChild(input);
    player.seek(30);
    pressKey("j", { target: input });
    expect(player.time).toBe(30);
    input.remove();
  });

  it("ctrlKey+j is ignored", () => {
    render(PlayerHost);
    flushSync();
    player.seek(30);
    pressKey("j", { ctrlKey: true });
    expect(player.time).toBe(30);
  });

  it("closed player does nothing", () => {
    render(PlayerHost);
    flushSync();
    const next = vi.fn();
    player.setNav({ next, prev: vi.fn(), canNext: () => true, canPrev: () => true });
    player.close();
    pressKey("N", { shiftKey: true });
    expect(next).not.toHaveBeenCalled();
  });

  it("mini mode also reacts to keys", () => {
    render(PlayerHost);
    flushSync();
    player.releaseSlot("v1");
    expect(player.mode).toBe("mini");
    player.seek(30);
    pressKey("j");
    expect(player.time).toBe(20);
  });
});
