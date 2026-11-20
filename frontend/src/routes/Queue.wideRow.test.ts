// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import App from "../App.svelte";
import queueSrc from "./Queue.svelte?raw";

function job(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    state: "queued",
    created_at: "2025-01-01T00:00:00Z",
    title: "Post " + id,
    source: "danbooru",
    target: "stash",
    progress: 0,
    ...extra,
  };
}

describe("Queue wide row", () => {
  beforeEach(() => {
    history.replaceState({}, "", "/queue");
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            items: [job("a", { post_id: "12345" }), job("b"), job("c", { source: null, post_id: null })],
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

  it("shows 'source #post_id' in the Source column, with the full text in title", async () => {
    render(App);
    await vi.waitFor(() => expect(document.querySelectorAll(".source").length).toBe(3));
    const cols = [...document.querySelectorAll<HTMLElement>(".source")];
    expect(cols[0].textContent).toBe("danbooru #12345");
    expect(cols[0].getAttribute("title")).toBe("danbooru #12345");
  });

  it("is null-safe: no post id, or no source, leaves clean text", async () => {
    render(App);
    await vi.waitFor(() => expect(document.querySelectorAll(".source").length).toBe(3));
    const cols = [...document.querySelectorAll<HTMLElement>(".source")];
    expect(cols[1].textContent).toBe("danbooru");
    expect(cols[2].textContent).toBe("");
    expect(document.body.textContent).not.toMatch(/undefined|null|#undefined/);
  });

  it("keeps 'source → target' in the narrow row, with the source word in its own span", async () => {
    render(App);
    await vi.waitFor(() => expect(document.querySelectorAll(".dest").length).toBe(3));
    const dest = document.querySelectorAll<HTMLElement>(".dest");
    expect(dest[0].textContent).toBe("danbooru → Stash");
    expect(dest[0].querySelector(".src-word")).toBeTruthy();
    expect(dest[2].textContent?.trim()).toBe("→ Stash");
  });

  it("CSS: container query at 1000px adds the Source column", () => {
    const css = queueSrc;
    expect(css).toMatch(/container-type:\s*inline-size/);
    expect(css).toMatch(/@container \(min-width: 1000px\)/);
    expect(css).toMatch(/56px minmax\(0, 1fr\) 200px 93px/);
  });
});
