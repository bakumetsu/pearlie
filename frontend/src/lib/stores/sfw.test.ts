// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createSfw } from "./sfw.svelte";

function makeRoot(): HTMLDivElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("createSfw", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    document.body.innerHTML = "";
    root = makeRoot();
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("defaults to false and root dataset is unset", () => {
    const sfw = createSfw(root);
    expect(sfw.on).toBe(false);
    expect(root.dataset.sfw).toBeUndefined();
  });

  it("toggle flips root.dataset.sfw", () => {
    const sfw = createSfw(root);

    sfw.toggle();
    expect(sfw.on).toBe(true);
    expect(root.dataset.sfw).toBe("on");

    sfw.toggle();
    expect(sfw.on).toBe(false);
    expect(root.dataset.sfw).toBeUndefined();
  });

  it("toggle clears data-sfw-shown from elements under root", () => {
    const sfw = createSfw(root);

    const img = document.createElement("img");
    img.setAttribute("data-sfw-shown", "1");
    root.appendChild(img);

    sfw.toggle();
    expect(sfw.on).toBe(true);
    expect(img.hasAttribute("data-sfw-shown")).toBe(false);
  });

  it("toggle calls onChange with true then false", () => {
    const sfw = createSfw(root);
    const onChange = vi.fn();
    sfw.onChange = onChange;

    sfw.toggle();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(true);

    sfw.toggle();
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("set(true) sets dataset and does not call onChange", () => {
    const sfw = createSfw(root);
    const onChange = vi.fn();
    sfw.onChange = onChange;

    sfw.set(true);
    expect(sfw.on).toBe(true);
    expect(root.dataset.sfw).toBe("on");
    expect(onChange).not.toHaveBeenCalled();
  });
});
