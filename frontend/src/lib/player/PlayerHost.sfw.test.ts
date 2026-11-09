// PlayerHost wraps the video and the stage bar in one data-sfw-group container
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

describe("PlayerHost sfw-group", () => {
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

  it("video and stage-bar share the same data-sfw-group ancestor", () => {
    render(PlayerHost);
    flushSync();
    const vg = document.querySelector("video[data-player]")?.closest("[data-sfw-group]");
    const bg = document.querySelector(".stage-bar")?.closest("[data-sfw-group]");
    expect(vg).not.toBeNull();
    expect(bg).toBe(vg);
  });
});
