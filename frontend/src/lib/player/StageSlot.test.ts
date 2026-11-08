import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import StageSlot from "./StageSlot.svelte";
import { player } from "./player.svelte";

class FakeRO {
  observe() {}
  disconnect() {}
}

const item = { id: "v1", title: "t", streamUrl: "/s", posterUrl: "/p", href: "/item/videos/v1" };

describe("StageSlot", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    player.open(item);
  });

  it("reports its rect and releases on destroy", () => {
    const rect = { x: 10, y: 20, width: 300, height: 200, top: 20, left: 10, right: 310, bottom: 220, toJSON() {} };
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(rect as DOMRect);
    const { unmount } = render(StageSlot, { id: "v1" });
    flushSync();
    expect(player.slot).toEqual({ x: 10, y: 20, w: 300, h: 200 });
    expect(player.mode).toBe("stage");
    unmount();
    expect(player.slot).toBeNull();
    expect(player.mode).not.toBe("stage");
  });
});
