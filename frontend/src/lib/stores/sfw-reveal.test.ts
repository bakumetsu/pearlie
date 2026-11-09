// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { installReveal } from "./sfw-reveal";

function makeRoot(sfwOn: boolean = true): HTMLDivElement {
  const root = document.createElement("div");
  if (sfwOn) root.dataset.sfw = "on";
  document.body.appendChild(root);
  return root;
}

describe("installReveal", () => {
  let root: HTMLDivElement;
  let img: HTMLImageElement;
  let uninstall: () => void;

  beforeEach(() => {
    document.body.innerHTML = "";
    root = makeRoot(true);
    img = document.createElement("img");
    img.src = "/p1.jpg";
    root.appendChild(img);
    uninstall = installReveal(root);
  });

  afterEach(() => {
    uninstall();
    document.body.innerHTML = "";
  });

  it("first click sets data-sfw-shown, prevents default, and stops propagation to parent bubble listener", () => {
    let bubbleHit = false;
    root.addEventListener("click", () => {
      bubbleHit = true;
    });

    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    img.dispatchEvent(event);

    expect(img.hasAttribute("data-sfw-shown")).toBe(true);
    expect(event.defaultPrevented).toBe(true);
    expect(bubbleHit).toBe(false);
  });

  it("second click on already-revealed img passes through", () => {
    const e1 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img.dispatchEvent(e1);
    expect(img.hasAttribute("data-sfw-shown")).toBe(true);

    let bubbleHit = false;
    root.addEventListener("click", () => {
      bubbleHit = true;
    });

    const e2 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img.dispatchEvent(e2);

    expect(e2.defaultPrevented).toBe(false);
    expect(bubbleHit).toBe(true);
  });

  it("click on <a> inside .tile reveals the tile's img", () => {
    const tile = document.createElement("div");
    tile.className = "tile";
    const a = document.createElement("a");
    const tileImg = document.createElement("img");
    tileImg.src = "/tile.jpg";
    a.appendChild(tileImg);
    tile.appendChild(a);
    root.appendChild(tile);

    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    a.dispatchEvent(event);

    expect(tileImg.hasAttribute("data-sfw-shown")).toBe(true);
    expect(event.defaultPrevented).toBe(true);
  });

  it("does nothing when SFW is off", () => {
    uninstall();
    document.body.innerHTML = "";
    const offRoot = makeRoot(false);
    const offImg = document.createElement("img");
    offImg.src = "/off.jpg";
    offRoot.appendChild(offImg);

    const uninstall2 = installReveal(offRoot);

    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    offImg.dispatchEvent(event);

    expect(offImg.hasAttribute("data-sfw-shown")).toBe(false);
    expect(event.defaultPrevented).toBe(false);

    uninstall2();
  });

  it("uninstall removes the handler", () => {
    const e1 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img.dispatchEvent(e1);
    expect(img.hasAttribute("data-sfw-shown")).toBe(true);

    uninstall();
    img.removeAttribute("data-sfw-shown");

    const e2 = new MouseEvent("click", { bubbles: true, cancelable: true });
    img.dispatchEvent(e2);

    expect(img.hasAttribute("data-sfw-shown")).toBe(false);
    expect(e2.defaultPrevented).toBe(false);
  });

  describe("page turn", () => {
    it("new src removes data-sfw-shown; restoring old src brings it back", () => {
      // Reveal the image
      const e1 = new MouseEvent("click", { bubbles: true, cancelable: true });
      img.dispatchEvent(e1);
      expect(img.hasAttribute("data-sfw-shown")).toBe(true);

      // Simulate page turn: change to a new src
      img.src = "/p2.jpg";
      img.dispatchEvent(new Event("load", { bubbles: true }));
      expect(img.hasAttribute("data-sfw-shown")).toBe(false);

      // Turn back: restore original src
      img.src = "/p1.jpg";
      img.dispatchEvent(new Event("load", { bubbles: true }));
      expect(img.hasAttribute("data-sfw-shown")).toBe(true);
    });
  });
});
