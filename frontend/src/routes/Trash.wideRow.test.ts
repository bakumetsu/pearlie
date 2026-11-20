// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import App from "../App.svelte";
import trashSrc from "./Trash.svelte?raw";

function entry(token: string, kind: string, size_bytes: number | null, days: number) {
  return {
    token,
    expires_at: new Date(Date.now() + days * 86_400_000 - 3_600_000).toISOString(),
    retention_days: 7,
    item: { kind, id: token, title: "Item " + token, size_bytes },
  };
}

describe("Trash wide row", () => {
  beforeEach(() => {
    history.replaceState({}, "", "/trash");
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            retention_days: 7,
            items: [
              entry("a", "video", 1_503_238_554, 5),
              entry("b", "image", 860_000_000, 2),
              entry("c", "image", null, 6),
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the formatted size, and an en dash for a null size", async () => {
    render(App);
    await vi.waitFor(() => expect(document.querySelectorAll(".cell.size").length).toBe(3));
    const sizes = [...document.querySelectorAll(".cell.size")].map((e) => e.textContent);
    expect(sizes).toEqual(["1.4 GB", "820.2 MB", "–"]);
  });

  it("shows kind and time left in their own cells", async () => {
    render(App);
    await vi.waitFor(() => expect(document.querySelectorAll(".cell.kind").length).toBe(3));
    expect(document.querySelector(".cell.kind")?.textContent).toBe("Stash Video");
    const left = [...document.querySelectorAll(".cell.left")].map((e) => e.textContent?.trim());
    expect(left[1]).toBe("2 days left");
    expect(document.querySelectorAll(".cell.left .dl.soon").length).toBe(1);
    expect(document.body.textContent).not.toMatch(/undefined|null|NaN/);
  });

  it("CSS: container query at 1000px, six-column grid, header and confirm padding", () => {
    expect(trashSrc).toMatch(/container-type:\s*inline-size/);
    expect(trashSrc).toMatch(/@container \(min-width: 1000px\)/);
    expect(trashSrc).toMatch(/56px minmax\(0, 1fr\) 140px 96px 140px calc\(2 \* 44px \+ 4px\)/);
    expect(trashSrc).toMatch(/padding-right:\s*var\(--sfw-clear\)/);
    expect(trashSrc).toMatch(/max-width:\s*var\(--measure\)/);
  });
});
