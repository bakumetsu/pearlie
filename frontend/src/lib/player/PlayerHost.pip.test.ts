import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { flushSync } from "svelte";
import PlayerHost from "./PlayerHost.svelte";
import { player } from "./player.svelte";

class FakeRO {
  observe() {}
  disconnect() {}
}

const item = { id: "v1", title: "t", streamUrl: "/s", posterUrl: "/p", href: "/item/videos/v1" };

describe("PlayerHost in PiP", () => {
  let handlers: Record<string, unknown>;

  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    vi.stubGlobal("MediaMetadata", class { constructor(public init: unknown) {} });
    handlers = {};
    Object.defineProperty(navigator, "mediaSession", {
      configurable: true,
      value: {
        metadata: null,
        setActionHandler: (a: string, fn: unknown) => { handlers[a] = fn; },
      },
    });
    player.open(item);
    player.onPlaying();
    player.releaseSlot("v1");
  });

  afterEach(() => {
    cleanup();
    player.setNav(null);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    player.close();
  });

  const video = () => document.querySelector<HTMLVideoElement>("video[data-player]")!;

  function captureStyles(): string[] {
    const seen: string[] = [];
    const orig = Object.getOwnPropertyDescriptor(CSSStyleDeclaration.prototype, "cssText")!;
    vi.spyOn(CSSStyleDeclaration.prototype, "cssText", "set").mockImplementation(function (this: CSSStyleDeclaration, v: string) {
      seen.push(v);
      orig.set!.call(this, v);
    });
    return seen;
  }

  it("hides the mini video box while PiP is on", () => {
    player.setSlot("v1", { x: 10, y: 20, w: 300, h: 200 });
    player.releaseSlot("v1");
    const seen = captureStyles();
    render(PlayerHost);
    flushSync();
    video().dispatchEvent(new Event("enterpictureinpicture"));
    flushSync();
    expect(player.pip).toBe(true);
    expect(seen[seen.length - 1]).toMatch(/display:\s*none/);
  });

  it("keeps previoustrack and nexttrack handlers while PiP is open with a queue", () => {
    player.setNav({ next: vi.fn(), prev: vi.fn(), canNext: () => true, canPrev: () => true });
    render(PlayerHost);
    flushSync();
    video().dispatchEvent(new Event("enterpictureinpicture"));
    flushSync();
    expect(player.pip).toBe(true);
    expect(typeof handlers["previoustrack"]).toBe("function");
    expect(typeof handlers["nexttrack"]).toBe("function");
  });

  it("has no track handlers without a queue", () => {
    render(PlayerHost);
    flushSync();
    expect(handlers["previoustrack"]).toBeNull();
    expect(handlers["nexttrack"]).toBeNull();
  });
});
