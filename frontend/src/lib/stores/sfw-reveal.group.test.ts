// @vitest-environment jsdom
// sfw-reveal group path: a [data-sfw-group] container reveals its video while the pointer is anywhere inside
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { installReveal } from "./sfw-reveal";

// ─── helpers ────────────────────────────────────────────────────────────────

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

function makeRoot() {
  const root = document.createElement("div");
  root.id = "root";
  root.dataset.sfw = "on";

  // tile path
  const tile = document.createElement("div");
  tile.className = "tile";
  const tileImg = document.createElement("img");
  tileImg.src = "/tile.jpg";
  tile.appendChild(tileImg);

  // group path
  const group = document.createElement("div");
  group.dataset.sfwGroup = "";
  const video = document.createElement("video");
  video.poster = "/p.jpg";
  const bar = document.createElement("div");
  bar.className = "bar";
  const btn = document.createElement("button");
  btn.textContent = "play";
  bar.appendChild(btn);
  group.appendChild(video);
  group.appendChild(bar);

  root.appendChild(tile);
  root.appendChild(group);
  document.body.appendChild(root);

  return { root, tile, tileImg, group, video, bar, btn };
}

// ─── fixture lifecycle ──────────────────────────────────────────────────────

let fixture: ReturnType<typeof makeRoot>;
let uninstall: (() => void) | null = null;

beforeEach(() => {
  fixture = makeRoot();
  uninstall = installReveal(fixture.root);
});

afterEach(() => {
  if (uninstall) uninstall();
  uninstall = null;
  fixture.root.remove();
  document.body.innerHTML = "";
});

// ─── tests ──────────────────────────────────────────────────────────────────

describe("sfw-reveal group", () => {
  it("mouse pointerover on the bar reveals the group video", () => {
    const { btn, video } = fixture;
    ptr("pointerover", btn, "mouse");
    expect(video.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("mouse pointerout from the video to the bar keeps the video revealed", () => {
    const { btn, video } = fixture;
    ptr("pointerover", btn, "mouse");
    expect(video.hasAttribute("data-sfw-shown")).toBe(true);
    ptr("pointerout", video, "mouse", { relatedTarget: btn });
    expect(video.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("mouse pointerout from the bar to outside hides the video", () => {
    const { btn, video } = fixture;
    ptr("pointerover", btn, "mouse");
    expect(video.hasAttribute("data-sfw-shown")).toBe(true);
    ptr("pointerout", btn, "mouse", { relatedTarget: document.body });
    expect(video.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("touch pointerdown inside the bar keeps revealed; pointerdown outside hides", () => {
    const { btn, video } = fixture;
    ptr("pointerover", btn, "mouse");
    expect(video.hasAttribute("data-sfw-shown")).toBe(true);
    ptr("pointerdown", btn, "touch");
    expect(video.hasAttribute("data-sfw-shown")).toBe(true);
    ptr("pointerdown", document.body, "touch");
    expect(video.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("tile path unchanged: pointerover img reveals, pointerout to body hides", () => {
    const { tileImg } = fixture;
    ptr("pointerover", tileImg, "mouse");
    expect(tileImg.hasAttribute("data-sfw-shown")).toBe(true);
    ptr("pointerout", tileImg, "mouse", { relatedTarget: document.body });
    expect(tileImg.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("touch click on bar button is not swallowed; touch click on video reveals (prevents default)", () => {
    const { btn, video } = fixture;
    ptr("pointerdown", btn, "touch");
    const clickBar = new MouseEvent("click", { bubbles: true, cancelable: true });
    btn.dispatchEvent(clickBar);
    expect(clickBar.defaultPrevented).toBe(false);

    ptr("pointerdown", video, "touch");
    const clickVideo = new MouseEvent("click", { bubbles: true, cancelable: true });
    video.dispatchEvent(clickVideo);
    expect(clickVideo.defaultPrevented).toBe(true);
  });
});
