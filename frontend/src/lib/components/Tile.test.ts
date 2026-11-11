// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import Tile from "./Tile.svelte";
import type { LibraryItem, WebItem } from "../api/client";
import { sfw } from "../stores/sfw.svelte";
import { options } from "../stores/options.svelte";

vi.mock("../stores/options.svelte", () => ({
  options: { values: null as unknown },
}));
import src from "./SectionRow.svelte?raw";

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

describe("Tile landscape", () => {
  const video: LibraryItem = {
    kind: "video", id: "v", title: "V", thumb_url: "/t.jpg",
    added_at: "2025-01-01T00:00:00Z", favorite: false,
  };

  it("landscape video gets one fixed 16 / 9 box", () => {
    const { container } = render(Tile, { item: video, href: "/x", landscape: true });
    expect(container.querySelector<HTMLElement>(".media")!.style.aspectRatio).toBe("16 / 9");
  });

  it("landscape does not change non-video kinds", () => {
    const { container } = render(Tile, { item: { ...video, kind: "image" }, href: "/x", landscape: true });
    expect(container.querySelector<HTMLElement>(".media")!.style.aspectRatio).toBe("2 / 3");
  });
});

describe("SectionRow scrollbar", () => {
  it("hides the horizontal scrollbar while keeping arrow buttons", () => {
    expect(src).toContain("scrollbar-width: none");
    expect(src).toContain("::-webkit-scrollbar");
    expect(src).toContain('class="strip no-scrollbar"');
    expect(src).toContain('aria-label="Scroll right"');
  });
});

describe("Tile onopenitem", () => {
  const item: LibraryItem = {
    kind: "image",
    id: "1",
    title: "T",
    thumb_url: "/t.jpg",
    added_at: "2025-01-01T00:00:00Z",
    favorite: false,
  };

  it("plain click on image tile calls onopenitem with item, not onnavigate, and prevents default", () => {
    const onopenitem = vi.fn();
    const onnavigate = vi.fn();
    const { container } = render(Tile, { item, href: "/x", onopenitem, onnavigate });
    const anchor = container.querySelector("a.tile")!;
    const evt = new MouseEvent("click", { bubbles: true, cancelable: true });
    anchor.dispatchEvent(evt);
    expect(onopenitem).toHaveBeenCalledWith(item);
    expect(onnavigate).not.toHaveBeenCalled();
    expect(evt.defaultPrevented).toBe(true);
  });

  it("ctrl-click calls onnavigate and not onopenitem", () => {
    const onopenitem = vi.fn();
    const onnavigate = vi.fn();
    const { container } = render(Tile, { item, href: "/x", onopenitem, onnavigate });
    const anchor = container.querySelector("a.tile")!;
    fireEvent.click(anchor, { ctrlKey: true });
    expect(onnavigate).toHaveBeenCalled();
    expect(onopenitem).not.toHaveBeenCalled();
  });

  it("video tile plain click calls onnavigate, not onopenitem", () => {
    const videoItem: LibraryItem = {
      kind: "video",
      id: "1",
      title: "T",
      thumb_url: "/t.jpg",
      added_at: "2025-01-01T00:00:00Z",
      favorite: false,
    };
    const onopenitem = vi.fn();
    const onnavigate = vi.fn();
    const { container } = render(Tile, { item: videoItem, href: "/x", onopenitem, onnavigate });
    const anchor = container.querySelector("a.tile")!;
    fireEvent.click(anchor);
    expect(onnavigate).toHaveBeenCalled();
    expect(onopenitem).not.toHaveBeenCalled();
  });

  it("without onopenitem, click calls onnavigate", () => {
    const onnavigate = vi.fn();
    const { container } = render(Tile, { item, href: "/x", onnavigate });
    const anchor = container.querySelector("a.tile")!;
    fireEvent.click(anchor);
    expect(onnavigate).toHaveBeenCalled();
  });

  it('anchor has data-key "image:1"', () => {
    const { container } = render(Tile, { item, href: "/x" });
    const anchor = container.querySelector("a.tile")!;
    expect(anchor.getAttribute("data-key")).toBe("image:1");
  });
});

describe("Tile warn-list in safe mode", () => {
  const warn = {
    source: "danbooru", post_id: "1", thumb_url: "/t.jpg", preview_url: "/p.jpg",
    title: null, tags: [], width: 1, height: 1, target: "stash", blur: { tag: "gore" },
  } as unknown as WebItem;

  afterEach(() => {
    delete document.documentElement.dataset.sfw;
    (options as { values: unknown }).values = null;
  });

  it("safe mode off: warn post shown blurred", () => {
    const { container } = render(Tile, { item: warn });
    expect(container.querySelector(".tile")).not.toBeNull();
    expect(container.querySelector("img.blur-img")).not.toBeNull();
  });

  it("safe mode on, switch off (default): warn post hidden", () => {
    sfw!.set(true);
    const { container } = render(Tile, { item: warn });
    expect(container.querySelector(".tile")).toBeNull();
  });

  it("safe mode on, switch on: warn post stays, blurred", () => {
    sfw!.set(true);
    (options as { values: unknown }).values = { allow_blurred_tags: true };
    const { container } = render(Tile, { item: warn });
    expect(container.querySelector(".tile")).not.toBeNull();
    expect(container.querySelector("img.blur-img")).not.toBeNull();
  });

  it("safe mode on: post without blur tag is unaffected", () => {
    sfw!.set(true);
    const { container } = render(Tile, { item: { ...warn, blur: null } as unknown as WebItem });
    expect(container.querySelector(".tile")).not.toBeNull();
  });
});
