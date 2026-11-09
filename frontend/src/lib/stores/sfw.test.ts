// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { loadSfw, saveSfw, createSfw, SFW_KEY } from "./sfw.svelte";

function makeStorage(initial: Record<string, string> = {}) {
  const store: Record<string, string> = { ...initial };
  return {
    getItem: vi.fn((key: string) => (key in store ? store[key] : null)),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
  };
}

function makeRoot(): HTMLDivElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("loadSfw", () => {
  it("returns false when no value is stored", () => {
    expect(loadSfw(makeStorage())).toBe(false);
  });

  it("returns true only for the string '1'", () => {
    expect(loadSfw(makeStorage({ [SFW_KEY]: "1" }))).toBe(true);
    expect(loadSfw(makeStorage({ [SFW_KEY]: "0" }))).toBe(false);
    expect(loadSfw(makeStorage({ [SFW_KEY]: "true" }))).toBe(false);
  });

  it("returns false when storage throws", () => {
    const throwing = {
      getItem: vi.fn(() => {
        throw new Error("SecurityError");
      }),
      setItem: vi.fn(() => {
        throw new Error("SecurityError");
      }),
    };
    expect(loadSfw(throwing)).toBe(false);
  });

  it("saveSfw does not throw when storage throws", () => {
    const throwing = {
      getItem: vi.fn(() => {
        throw new Error("SecurityError");
      }),
      setItem: vi.fn(() => {
        throw new Error("SecurityError");
      }),
    };
    expect(() => saveSfw(true, throwing)).not.toThrow();
    expect(() => saveSfw(false, throwing)).not.toThrow();
  });
});

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
    const sfw = createSfw(makeStorage(), root);
    expect(sfw.on).toBe(false);
    expect(root.dataset.sfw).toBeUndefined();
  });

  it("toggle flips root.dataset.sfw and persists '1' / '0'", () => {
    const store = makeStorage();
    const sfw = createSfw(store, root);

    sfw.toggle();
    expect(sfw.on).toBe(true);
    expect(root.dataset.sfw).toBe("on");
    expect(store.setItem).toHaveBeenCalledWith(SFW_KEY, "1");

    sfw.toggle();
    expect(sfw.on).toBe(false);
    expect(root.dataset.sfw).toBeUndefined();
    expect(store.setItem).toHaveBeenCalledWith(SFW_KEY, "0");
  });

  it("toggle clears data-sfw-shown from elements under root", () => {
    const store = makeStorage();
    const sfw = createSfw(store, root);

    const img = document.createElement("img");
    img.setAttribute("data-sfw-shown", "1");
    root.appendChild(img);

    sfw.toggle();
    expect(sfw.on).toBe(true);
    expect(img.hasAttribute("data-sfw-shown")).toBe(false);
  });
});
