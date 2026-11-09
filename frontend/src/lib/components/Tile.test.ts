// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import Tile from "./Tile.svelte";
import type { LibraryItem } from "../api/client";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

afterEach(() => {
  cleanup();
});

describe("Tile", () => {
  it.each(["image", "video", "series", "book"] as const)(
    "renders .media with aspect-ratio 2 / 3 for kind=%s",
    (kind) => {
      const item: LibraryItem = {
        kind,
        id: "1",
        title: "Test",
        thumb_url: "/t.jpg",
        added_at: "2025-01-01T00:00:00Z",
        favorite: false,
      };

      const { container } = render(Tile, { item, href: "/x" });
      const media = container.querySelector<HTMLElement>(".media")!;
      expect(media.style.aspectRatio).toBe("2 / 3");
    },
  );
});

describe("SectionRow scrollbar", () => {
  it("hides the horizontal scrollbar while keeping arrow buttons", () => {
    const src = readFileSync(
      fileURLToPath(new URL("./SectionRow.svelte", import.meta.url)),
      "utf-8",
    );
    expect(src).toContain("scrollbar-width: none");
    expect(src).toContain("::-webkit-scrollbar");
    expect(src).toContain('class="strip no-scrollbar"');
    expect(src).toContain('aria-label="Scroll right"');
  });
});
