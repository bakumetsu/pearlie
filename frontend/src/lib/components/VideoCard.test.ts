// @vitest-environment jsdom
// Tests for VideoCard preview behaviour (T-36)
import { render, cleanup } from "@testing-library/svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import VideoCard from "./VideoCard.svelte";
import cardSrc from "./VideoCard.svelte?raw";
import { videoPreview } from "../stores/videoPreview.svelte";
import type { LibraryItem } from "../api/client";

function ptr(el: Element, type: string, pointerType: string, x = 0, y = 0): MouseEvent {
  const ev = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y });
  Object.defineProperty(ev, "pointerType", { value: pointerType });
  el.dispatchEvent(ev);
  return ev;
}

function setMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    value: vi.fn().mockReturnValue({ matches }),
    writable: true,
    configurable: true,
  });
}

const item: LibraryItem = {
  kind: "video",
  id: "v1",
  title: "T",
  thumb_url: "/t.jpg",
  added_at: "2025-01-01T00:00:00Z",
  favorite: false,
  preview_url: "/p.mp4",
  height: 1080,
  duration_s: 65,
  studio: "S",
  date: "2024-05-01",
};

const baseProps = {
  item,
  variant: "grid" as const,
  aspectRatio: "2 / 3",
  blurred: false,
  meta: "",
  onmediaclick: vi.fn(),
  onmediakeydown: vi.fn(),
};

beforeEach(() => {
  vi.useFakeTimers();
  videoPreview.reset();
  document.documentElement.removeAttribute("data-sfw");
  setMatchMedia(false);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("VideoCard", () => {
  // ── 1. Static rendering ──────────────────────────────────────────────

  it("renders poster, 1080p badge, 1:05 duration, and subline", () => {
    const { container } = render(VideoCard, baseProps);
    const poster = container.querySelector("img");
    expect(poster).not.toBeNull();
    expect(poster!.getAttribute("src")).toBe("/t.jpg");
    expect(container.textContent).toContain("1080p");
    expect(container.textContent).toContain("1:05");
    const sub = container.querySelector(".sub");
    expect(sub).not.toBeNull();
    expect(sub!.textContent).toBe("S - 2024-05-01");
  });

  it("shows 4K badge for height 2160", () => {
    const item4k: LibraryItem = { ...item, height: 2160 };
    const { container } = render(VideoCard, { ...baseProps, item: item4k });
    expect(container.textContent).toContain("4K");
    expect(container.textContent).not.toContain("1080p");
  });

  it("renders no .sub when studio and date are missing", () => {
    const itemBare: LibraryItem = { ...item, studio: "", date: "" };
    const { container } = render(VideoCard, { ...baseProps, item: itemBare });
    expect(container.querySelector(".sub")).toBeNull();
  });

  // ── 2. Mouse preview enter / leave ──────────────────────────────────

  it("mounts a video on pointerenter and removes it on pointerleave", async () => {
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerenter", "mouse");
    await Promise.resolve();
    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video!.getAttribute("src")).toBe("/p.mp4");

    ptr(media, "pointerleave", "mouse");
    await Promise.resolve();
    expect(container.querySelector("video")).toBeNull();
  });

  // ── 3. Touch: 500 ms delay then click swallow ───────────────────────

  it("delays video mount 500 ms on touch and swallows the trailing click", async () => {
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerdown", "touch");
    await Promise.resolve();

    vi.advanceTimersByTime(499);
    await Promise.resolve();
    expect(container.querySelector("video")).toBeNull();

    vi.advanceTimersByTime(1);
    await Promise.resolve();
    expect(container.querySelector("video")).not.toBeNull();

    // The synthetic click that follows a touch press should be swallowed.
    const clickEv = new MouseEvent("click", { bubbles: true });
    media.dispatchEvent(clickEv);
    await Promise.resolve();
    expect(baseProps.onmediaclick).not.toHaveBeenCalled();
  });

  // ── 4. Touch: pointermove > 10 px cancels ───────────────────────────

  it("cancels the preview when pointer moves more than 10 px before 500 ms", async () => {
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerdown", "touch", 0, 0);
    await Promise.resolve();

    ptr(media, "pointermove", "touch", 20, 0);
    await Promise.resolve();

    vi.advanceTimersByTime(600);
    await Promise.resolve();
    expect(container.querySelector("video")).toBeNull();
  });

  // ── 5. Single preview at a time ─────────────────────────────────────

  it("keeps only one video mounted when multiple cards receive enter", async () => {
    const item2: LibraryItem = { ...item, id: "v2" };
    const { container: c1 } = render(VideoCard, baseProps);
    const { container: c2 } = render(VideoCard, { ...baseProps, item: item2 });

    const media1 = c1.querySelector(".media")!;
    const media2 = c2.querySelector(".media")!;

    ptr(media1, "pointerenter", "mouse");
    await Promise.resolve();
    expect(document.querySelectorAll("video")).toHaveLength(1);

    ptr(media2, "pointerenter", "mouse");
    await Promise.resolve();
    expect(document.querySelectorAll("video")).toHaveLength(1);
    expect(c1.querySelector("video")).toBeNull();
    expect(c2.querySelector("video")).not.toBeNull();
  });

  // ── 6. Reduced motion ───────────────────────────────────────────────

  it("does not mount a video when prefers-reduced-motion matches", async () => {
    setMatchMedia(true);
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerenter", "mouse");
    await Promise.resolve();
    expect(container.querySelector("video")).toBeNull();
  });

  // ── 7. SFW gate ─────────────────────────────────────────────────────

  it("with data-sfw=on blocks video until poster carries data-sfw-shown", async () => {
    document.documentElement.dataset.sfw = "on";
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;
    const poster = container.querySelector("img")!;

    ptr(media, "pointerenter", "mouse");
    await Promise.resolve();
    expect(container.querySelector("video")).toBeNull();

    poster.setAttribute("data-sfw-shown", "1");
    await Promise.resolve();
    await Promise.resolve(); // second microtask for MutationObserver

    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video!.getAttribute("data-sfw-shown")).toBe("1");
  });

  // ── 8. Unmount clears active preview ────────────────────────────────

  it("clears the active preview on unmount (mouse)", async () => {
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerenter", "mouse");
    await Promise.resolve();
    expect(videoPreview.isActive("v1")).toBe(true);

    cleanup();
    expect(videoPreview.isActive("v1")).toBe(false);
  });

  it("clears the pending touch preview on unmount before the 500 ms timer", async () => {
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerdown", "touch");
    await Promise.resolve();

    cleanup();
    vi.advanceTimersByTime(600);
    await Promise.resolve();
    expect(videoPreview.isActive("v1")).toBe(false);
  });

  // ── 9. Video error removes video, keeps poster ──────────────────────

  it("removes the video and keeps the poster when the video errors", async () => {
    const { container } = render(VideoCard, baseProps);
    const media = container.querySelector(".media")!;

    ptr(media, "pointerenter", "mouse");
    await Promise.resolve();
    const video = container.querySelector("video")!;

    video.dispatchEvent(new Event("error"));
    await Promise.resolve();

    expect(container.querySelector("video")).toBeNull();
    expect(container.querySelector("img")).not.toBeNull();
  });

  // ── 10. Rule-blurred card keeps its preview blurred ─────────────────

  it("blurs the preview video when the card is rule-blurred", async () => {
    const { container } = render(VideoCard, {
      ...baseProps,
      item: { ...item, blur: { tag: "gore" } },
      blurred: true,
    });
    const media = container.querySelector(".media")!;

    ptr(media, "pointerenter", "mouse");
    await Promise.resolve();

    const video = container.querySelector("video")!;
    expect(video).not.toBeNull();
    expect(video.classList.contains("blur-img")).toBe(true);
  });

  it("landscape adds the .landscape class on .media and the CSS letterboxes with object-fit: contain", () => {
    const { container } = render(VideoCard, { ...baseProps, aspectRatio: "16 / 9", landscape: true });
    expect(container.querySelector(".media")!.classList.contains("landscape")).toBe(true);
    expect(cardSrc).toMatch(/\.media\.landscape img,\s*\.media\.landscape video\s*\{\s*object-fit: contain;/);
  });

  it("without landscape the .media has no .landscape class", () => {
    const { container } = render(VideoCard, baseProps);
    expect(container.querySelector(".media")!.classList.contains("landscape")).toBe(false);
  });
});
