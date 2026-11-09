import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
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
