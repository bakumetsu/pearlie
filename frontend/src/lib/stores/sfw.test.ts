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

describe("createSfw hint", () => {
  const mem = (init: Record<string, string> = {}) => {
    const data = { ...init };
    return {
      data,
      getItem: (k: string) => data[k] ?? null,
      setItem: (k: string, v: string) => { data[k] = v; },
    };
  };

  it("starts on from the stored hint, synchronously", () => {
    document.body.innerHTML = "";
    const root = document.createElement("div");
    const sfw = createSfw(root, mem({ "pearlie.sfw.hint": "1" }));
    expect(sfw.on).toBe(true);
    expect(root.dataset.sfw).toBe("on");
  });

  it("set and toggle update the hint", () => {
    const storage = mem({ "pearlie.sfw.hint": "1" });
    const sfw = createSfw(document.createElement("div"), storage);
    sfw.set(false);
    expect(storage.data["pearlie.sfw.hint"]).toBe("0");
    sfw.toggle();
    expect(storage.data["pearlie.sfw.hint"]).toBe("1");
  });

  it("a stale hint is overridden by set()", () => {
    const sfw = createSfw(document.createElement("div"), mem({ "pearlie.sfw.hint": "1" }));
    sfw.set(false);
    expect(sfw.on).toBe(false);
  });

  it("throwing storage does not break the store", () => {
    const bad = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
    };
    const sfw = createSfw(document.createElement("div"), bad);
    expect(sfw.on).toBe(false);
    sfw.toggle();
    expect(sfw.on).toBe(true);
    sfw.set(false);
    expect(sfw.on).toBe(false);
  });
});
