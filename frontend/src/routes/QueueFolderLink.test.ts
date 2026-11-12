// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";
import App from "../App.svelte";

function job(id: string, error: string, error_code: string) {
  return {
    id,
    state: "failed",
    created_at: "2025-01-01T00:00:00Z",
    title: "Post " + id,
    source: "danbooru",
    target: "stash",
    progress: 0,
    error,
    error_code,
  };
}

describe("Queue failed save-folder job", () => {
  beforeEach(() => {
    history.replaceState({}, "", "/queue");
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            items: [
              job("a", "folder is not inside a Stash library path", "outside_library"),
              job("b", "Timeout", "download_failed"),
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

  it("links only the outside-library failure to Save folders", async () => {
    render(App);
    const link = await screen.findByRole("link", { name: "Set the save folder" });
    expect(link.getAttribute("href")).toBe("/options/save-folders");
    expect(screen.getAllByRole("link", { name: "Set the save folder" })).toHaveLength(1);
  });
});
