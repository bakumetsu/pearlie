// @vitest-environment jsdom
// sfw-reveal hover delay (T-42)
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { installReveal, REVEAL_DELAY_MS } from "./sfw-reveal";

// ─── helpers ────────────────────────────────────────────────────────────────

function makeRoot() {
  const root = document.createElement("div");
  root.id = "root";
  root.dataset.sfw = "on";

  const tile1 = document.createElement("div");
  tile1.className = "tile";
  const link1 = document.createElement("a");
  link1.href = "#";
  const img1 = document.createElement("img");
  img1.src = "/t1.jpg";
  link1.appendChild(img1);
  tile1.appendChild(link1);

  const tile2 = document.createElement("div");
  tile2.className = "tile";
  const link2 = document.createElement("a");
  link2.href = "#";
  const img2 = document.createElement("img");
  img2.src = "/t2.jpg";
  link2.appendChild(img2);
  tile2.appendChild(link2);

  const standalone = document.createElement("img");
  standalone.src = "/standalone.jpg";

  root.appendChild(tile1);
  root.appendChild(tile2);
  root.appendChild(standalone);
  document.body.appendChild(root);

  return { root, tile1, link1, img1, tile2, link2, img2, standalone };
}

function ptr(
  type: string,
  target: EventTarget,
  pointerType: string,
  init?: { relatedTarget?: EventTarget | null },
) {
  const ev = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    relatedTarget: (init?.relatedTarget ?? null) as unknown as Node,
  } as MouseEventInit);
  Object.defineProperty(ev, "pointerType", { value: pointerType });
  if (init?.relatedTarget !== undefined) {
    Object.defineProperty(ev, "relatedTarget", { value: init.relatedTarget });
  }
  target.dispatchEvent(ev);
  return ev;
}

function focusEv(type: string, target: EventTarget, relatedTarget: EventTarget | null) {
  const ev = new FocusEvent(type, { bubbles: true, relatedTarget });
  target.dispatchEvent(ev);
  return ev;
}

// ─── fixture lifecycle ──────────────────────────────────────────────────────

let fixture: ReturnType<typeof makeRoot>;
let uninstall: (() => void) | null = null;

beforeEach(() => {
  vi.useFakeTimers();
  fixture = makeRoot();
  uninstall = installReveal(fixture.root);
});

afterEach(() => {
  vi.useRealTimers();
  if (uninstall) uninstall();
  uninstall = null;
  document.body.innerHTML = "";
});

// ─── tests ──────────────────────────────────────────────────────────────────

describe("sfw-reveal hover delay", () => {
  it("1. mouse pointerover: not shown at delay-1, shown at delay", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    vi.advanceTimersByTime(REVEAL_DELAY_MS - 1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
    vi.advanceTimersByTime(1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("2. pointerout before delay cancels pending reveal", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    vi.advanceTimersByTime(100);
    ptr("pointerout", img1, "mouse", { relatedTarget: document.body });
    vi.advanceTimersByTime(300); // total 400 ms
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("3. pointerout to outside hides immediately (no timer advance)", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    vi.advanceTimersByTime(REVEAL_DELAY_MS);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    ptr("pointerout", img1, "mouse", { relatedTarget: document.body });
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("4. pointer moves between imgs: timer restarts on new target", () => {
    const { img1, img2 } = fixture;

    ptr("pointerover", img1, "mouse");
    vi.advanceTimersByTime(100);

    // Leave img1 for img2
    ptr("pointerout", img1, "mouse", { relatedTarget: img2 });
    ptr("pointerover", img2, "mouse");

    // REVEAL_DELAY_MS - 1 ms after pointerover img2 — still not shown
    vi.advanceTimersByTime(REVEAL_DELAY_MS - 1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
    expect(img2.hasAttribute("data-sfw-shown")).toBe(false);

    // 1 more ms (total REVEAL_DELAY_MS) — img2 shown, img1 not
    vi.advanceTimersByTime(1);
    expect(img2.hasAttribute("data-sfw-shown")).toBe(true);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("5. touch tap shows immediately (no timer advance)", () => {
    const { img1 } = fixture;

    ptr("pointerdown", img1, "touch");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    img1.dispatchEvent(click);

    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("6. focusin reveals after delay; focusout before delay cancels", () => {
    const { link1, img1 } = fixture;

    // Reveal after delay
    focusEv("focusin", link1, null);
    vi.advanceTimersByTime(REVEAL_DELAY_MS - 1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
    vi.advanceTimersByTime(1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    // Hide, then focusout before delay cancels
    focusEv("focusout", link1, document.body);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    focusEv("focusin", link1, null);
    vi.advanceTimersByTime(100);
    focusEv("focusout", link1, document.body);
    vi.advanceTimersByTime(300); // total 400 ms
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("7. uninstall clears the pending timer", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    uninstall!();
    uninstall = null;
    vi.advanceTimersByTime(400);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("8. pen pointer behaves like mouse (shown after delay)", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "pen");
    vi.advanceTimersByTime(REVEAL_DELAY_MS - 1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
    vi.advanceTimersByTime(1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
  });
});
