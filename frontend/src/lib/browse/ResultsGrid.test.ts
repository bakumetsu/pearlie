// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import ResultsGrid from "./ResultsGrid.svelte";
import type { LibraryItem, WebItem } from "../api/client";

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Item = LibraryItem | WebItem;

function lib(id: string, extra: object = {}): LibraryItem {
  return {
    kind: "image",
    id,
    title: id,
    thumb_url: "/t/" + id,
    favorite: false,
    added_at: "2026-01-01",
    ...extra,
  } as LibraryItem;
}

function web(id: string): WebItem {
  return { source: "danbooru", post_id: id, thumb_url: "/t/" + id, preview_url: "/p/" + id, title: null, width: 100, height: 100, target: "stash" };
}

const defaultProps = {
  zoom: 3,
  loading: false,
  skeletons: 12,
  saveStates: {},
  onsave: () => {},
  onnavigate: () => {},
};

describe("ResultsGrid", () => {
  it("grid mode: container has .grid and one .tile.grid per item", () => {
    const items: Item[] = [lib("a"), lib("b"), lib("c")];
    const { container } = render(ResultsGrid, { ...defaultProps, items, mode: "grid" });
    expect(container.querySelector(".grid")).not.toBeNull();
    expect(container.querySelectorAll(".tile.grid")).toHaveLength(3);
  });

  it("list mode: .list exists, tiles have class list, --list-thumb is 80px", () => {
    const items: Item[] = [lib("a"), lib("b")];
    const { container } = render(ResultsGrid, { ...defaultProps, items, mode: "list" });
    expect(container.querySelector(".list")).not.toBeNull();
    const tiles = container.querySelectorAll<HTMLElement>(".tile");
    expect(tiles.length).toBe(2);
    for (const t of tiles) {
      expect(t.classList.contains("list")).toBe(true);
    }
    const root = container.querySelector<HTMLElement>(".rg")!;
    expect(root.style.getPropertyValue("--list-thumb")).toBe("80px");
  });

  it("wall mode: .wall-row exists and each tile has class wall", () => {
    const items: Item[] = [lib("a"), lib("b"), lib("c")];
    const { container } = render(ResultsGrid, { ...defaultProps, items, mode: "wall" });
    expect(container.querySelector(".wall-row")).not.toBeNull();
    const tiles = container.querySelectorAll<HTMLElement>(".tile");
    expect(tiles.length).toBe(3);
    for (const t of tiles) {
      expect(t.classList.contains("wall")).toBe(true);
    }
  });

  it("masonry mode: .masonry exists, .mcol count >= 1, all items appear exactly once", () => {
    const items: Item[] = [lib("a"), lib("b"), lib("c"), lib("d")];
    const { container } = render(ResultsGrid, { ...defaultProps, items, mode: "masonry" });
    expect(container.querySelector(".masonry")).not.toBeNull();
    expect(container.querySelectorAll(".mcol").length).toBeGreaterThanOrEqual(1);
    const tiles = container.querySelectorAll<HTMLElement>(".tile");
    expect(tiles.length).toBe(4);
    for (const t of tiles) {
      expect(t.classList.contains("masonry")).toBe(true);
    }
    // every item appears exactly once
    const srcs = Array.from(container.querySelectorAll("img")).map((i) => i.getAttribute("src"));
    expect([...srcs].sort()).toEqual(["/t/a", "/t/b", "/t/c", "/t/d"]);
  });

  it("loading true: renders 12 .skeleton elements and no .tile", () => {
    const items: Item[] = [lib("a")];
    const { container } = render(ResultsGrid, {
      ...defaultProps,
      items,
      mode: "grid",
      loading: true,
    });
    expect(container.querySelectorAll(".skeleton")).toHaveLength(12);
    expect(container.querySelectorAll(".tile")).toHaveLength(0);
  });

  it("web item in grid mode: clicking Save calls onsave once with that item", () => {
    const item = web("42");
    const items: Item[] = [item];
    const onsave = vi.fn();
    const { container } = render(ResultsGrid, {
      ...defaultProps,
      items,
      mode: "grid",
      onsave,
    });
    const btn = container.querySelector<HTMLButtonElement>("button.save-btn")!;
    btn.click();
    expect(onsave).toHaveBeenCalledTimes(1);
    expect(onsave).toHaveBeenCalledWith(item);
  });
});
