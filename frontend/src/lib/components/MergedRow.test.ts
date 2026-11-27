// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import MergedRow from "./MergedRow.svelte";
import tileSrc from "./Tile.svelte?raw";
import type { WebItem } from "../api/client";

afterEach(() => cleanup());

const web = (source: string, id: string) =>
  ({ source, post_id: id, thumb_url: "/t.jpg", preview_url: "/p.jpg", media_kind: "image", width: 1, height: 1, target: "stash", saveable: true, owned: false }) as unknown as WebItem;

describe("MergedRow", () => {
  it("shows the title, the See all arrow to the merged list, and a site letter on every tile", () => {
    const { container, getByText } = render(MergedRow, { items: [web("danbooru", "1"), web("gelbooru", "2")], status: "done" });
    expect(getByText("Latest from your sites")).toBeTruthy();
    const arrow = container.querySelector<HTMLAnchorElement>("a.see-all")!;
    expect(arrow.getAttribute("href")).toBe("/see-all?source=merged");
    expect(arrow.getAttribute("aria-label")).toBe("See all");
    const letters = [...container.querySelectorAll(".site-badge")].map((b) => b.textContent);
    expect(letters).toEqual(["D", "G"]);
    expect(container.querySelector(".site-badge")!.getAttribute("aria-hidden")).toBe("true");
  });

  it("has no status text and no live region", () => {
    const { container } = render(MergedRow, { items: [web("danbooru", "1")], status: "done" });
    expect(container.querySelector("[aria-live], [role=status], [role=alert]")).toBeNull();
    expect(container.textContent).not.toMatch(/\b(gelbooru|missing|pending|late|failed)\b/i);
  });

  it("loading shows a busy skeleton and no tiles", () => {
    const { container } = render(MergedRow, { items: [], status: "loading" });
    expect(container.querySelector("[aria-busy=true]")).toBeTruthy();
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
    expect(container.querySelector(".tile")).toBeNull();
  });

  it("an error shows the row error box with one Retry", () => {
    const { container } = render(MergedRow, { items: [], status: "error", error: "boom" });
    expect(container.querySelector(".error-msg")!.textContent).toBe("boom");
    expect(container.querySelectorAll(".retry-btn")).toHaveLength(1);
  });

  it("empty shows one line and the hidden-by-rules link", () => {
    const { container, getByText } = render(MergedRow, { items: [], status: "done", hidden: 4 });
    expect(getByText("Nothing to show. The sites gave no posts, or rules hid them.")).toBeTruthy();
    expect(container.querySelector(".footer a")!.textContent).toBe("4 hidden by rules");
  });
});

describe("Tile badge", () => {
  it("is decorative and takes no pointer events", () => {
    expect(tileSrc).toContain('class="site-badge" aria-hidden="true"');
    expect(tileSrc).toContain("pointer-events: none");
  });
});
