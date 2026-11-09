// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import Tile from "./Tile.svelte";
import type { LibraryItem } from "../api/client";

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
