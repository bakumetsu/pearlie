// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { installReveal, resetReveals } from "./sfw-reveal";

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
  fixture = makeRoot();
  uninstall = installReveal(fixture.root);
});

afterEach(() => {
  if (uninstall) uninstall();
  uninstall = null;
  document.body.innerHTML = "";
});

// ─── tests ──────────────────────────────────────────────────────────────────

describe("sfw-reveal transient", () => {
  it("1. mouse pointerover reveals tile img; pointerout to outside hides", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    ptr("pointerout", img1, "mouse", { relatedTarget: document.body });
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("2. mouse pointerout within same tile keeps revealed", () => {
    const { img1, link1 } = fixture;

    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    // pointerout from img, relatedTarget is the <a> (still inside tile)
    ptr("pointerout", img1, "mouse", { relatedTarget: link1 });
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("3. mouse click is never intercepted", () => {
    const { img1, root } = fixture;

    ptr("pointerover", img1, "mouse");

    let bubbleHit = false;
    root.addEventListener("click", () => { bubbleHit = true; });

    const ev = new MouseEvent("click", { bubbles: true, cancelable: true });
    img1.dispatchEvent(ev);

    expect(ev.defaultPrevented).toBe(false);
    expect(bubbleHit).toBe(true);
  });

  it("4. focusin on tile <a> reveals; focusout outside hides", () => {
    const { link1, img1 } = fixture;

    focusEv("focusin", link1, null);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    focusEv("focusout", link1, document.body);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("5. touch tap: first tap reveals & prevents; second tap passes", () => {
    const { img1, root } = fixture;

    // First tap
    ptr("pointerdown", img1, "touch");
    let bubbleHit1 = false;
    root.addEventListener("click", () => { bubbleHit1 = true; });

    const click1 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img1.dispatchEvent(click1);

    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    expect(click1.defaultPrevented).toBe(true);
    expect(bubbleHit1).toBe(false); // stopPropagation → root bubble not hit

    // Second tap
    root.removeEventListener("click", () => { bubbleHit1 = true; });
    ptr("pointerdown", img1, "touch");
    let bubbleHit2 = false;
    root.addEventListener("click", () => { bubbleHit2 = true; });

    const click2 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img1.dispatchEvent(click2);

    expect(click2.defaultPrevented).toBe(false);
    expect(bubbleHit2).toBe(true);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("6. touch tap tile1 then tile2 → only tile2 shown", () => {
    const { img1, img2 } = fixture;

    // Tap tile 1
    ptr("pointerdown", img1, "touch");
    const c1 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img1.dispatchEvent(c1);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    // Tap tile 2
    ptr("pointerdown", img2, "touch");
    const c2 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img2.dispatchEvent(c2);

    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
    expect(img2.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("7. touch pointerdown/click outside tile hides", () => {
    const { img1, standalone } = fixture;

    // Reveal via touch tap
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    // pointerdown on standalone (outside any tile)
    ptr("pointerdown", standalone, "touch");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // Reveal again
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    // click on outside element also hides
    ptr("pointerdown", standalone, "touch");
    const outsideClick = new MouseEvent("click", { bubbles: true, cancelable: true });
    standalone.dispatchEvent(outsideClick);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("8. scroll / pagehide / visibilitychange / hashchange / popstate hide", () => {
    const { img1 } = fixture;

    // scroll
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    window.dispatchEvent(new Event("scroll"));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // pagehide
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    window.dispatchEvent(new Event("pagehide"));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // visibilitychange
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });

    // hashchange
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    window.dispatchEvent(new Event("hashchange"));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // popstate
    ptr("pointerdown", img1, "touch");
    img1.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    window.dispatchEvent(new Event("popstate"));
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("9. touch tap after focusin: focusin ignored, click reveals & prevents", () => {
    const { link1, img1 } = fixture;

    ptr("pointerdown", link1, "touch");
    focusEv("focusin", link1, null);

    // focusin was ignored (lastPointerType === "touch"), so not revealed yet
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    link1.dispatchEvent(click);

    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);
    expect(click.defaultPrevented).toBe(true);
  });

  it("10. element reuse: changing src hides after microtask", async () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    img1.src = "/other.jpg";
    await new Promise((r) => setTimeout(r, 0));

    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("11. standalone img: hover reveals/hides; touch first tap prevented, second passes", () => {
    const { standalone, root } = fixture;

    // Hover
    ptr("pointerover", standalone, "mouse");
    expect(standalone.hasAttribute("data-sfw-shown")).toBe(true);

    ptr("pointerout", standalone, "mouse", { relatedTarget: document.body });
    expect(standalone.hasAttribute("data-sfw-shown")).toBe(false);

    // Touch first tap
    ptr("pointerdown", standalone, "touch");
    let bubbleHit1 = false;
    root.addEventListener("click", () => { bubbleHit1 = true; });
    const click1 = new MouseEvent("click", { bubbles: true, cancelable: true });
    standalone.dispatchEvent(click1);

    expect(standalone.hasAttribute("data-sfw-shown")).toBe(true);
    expect(click1.defaultPrevented).toBe(true);
    expect(bubbleHit1).toBe(false);

    // Touch second tap
    root.removeEventListener("click", () => { bubbleHit1 = true; });
    ptr("pointerdown", standalone, "touch");
    let bubbleHit2 = false;
    root.addEventListener("click", () => { bubbleHit2 = true; });
    const click2 = new MouseEvent("click", { bubbles: true, cancelable: true });
    standalone.dispatchEvent(click2);

    expect(click2.defaultPrevented).toBe(false);
    expect(bubbleHit2).toBe(true);
    expect(standalone.hasAttribute("data-sfw-shown")).toBe(true);
  });

  it("12. SFW off: hover, focus, touch click do nothing", () => {
    const { img1, link1, standalone, root } = fixture;

    // Remove the sfw attribute
    root.removeAttribute("data-sfw");

    // Hover
    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // Focus
    focusEv("focusin", link1, null);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // Touch click
    ptr("pointerdown", standalone, "touch");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    standalone.dispatchEvent(click);
    expect(standalone.hasAttribute("data-sfw-shown")).toBe(false);
    expect(click.defaultPrevented).toBe(false);
  });

  it("13. uninstall removes handlers and clears shown attribute", () => {
    const { img1 } = fixture;

    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    uninstall!();
    uninstall = null;

    // Attribute cleared by uninstall's internal hide()
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);

    // Hover after uninstall does nothing
    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("14. img without src is ignored", () => {
    const { tile1 } = fixture;

    const noSrcImg = document.createElement("img");
    // no src attribute
    const a = document.createElement("a");
    a.href = "#";
    a.appendChild(noSrcImg);
    tile1.replaceChild(a, tile1.firstElementChild!);

    ptr("pointerover", noSrcImg, "mouse");
    expect(noSrcImg.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("15. resetReveals(root) removes data-sfw-shown", () => {
    const { img1, root } = fixture;

    ptr("pointerover", img1, "mouse");
    expect(img1.hasAttribute("data-sfw-shown")).toBe(true);

    // Reveal img2 via a second mechanism (mouse pointerover on img2)
    // But reveal() first hides the previous, so only one can be shown.
    // Let's just test with one.
    resetReveals(root);
    expect(img1.hasAttribute("data-sfw-shown")).toBe(false);
  });
});
