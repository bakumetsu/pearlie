// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { createRail } from "./rail.svelte";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
  };
}

describe("createRail", () => {
  it("starts expanded with no root flag", () => {
    const root = document.createElement("div");
    const rail = createRail(root, memoryStorage());
    expect(rail.collapsed).toBe(false);
    expect(root.dataset.rail).toBeUndefined();
  });

  it("toggle sets the root flag and saves the choice", () => {
    const root = document.createElement("div");
    const storage = memoryStorage();
    const rail = createRail(root, storage);
    rail.toggle();
    expect(rail.collapsed).toBe(true);
    expect(root.dataset.rail).toBe("hidden");
    expect(storage.data["pearlie.rail.collapsed"]).toBe("1");
    rail.toggle();
    expect(root.dataset.rail).toBeUndefined();
    expect(storage.data["pearlie.rail.collapsed"]).toBe("0");
  });

  it("restores the saved choice", () => {
    const root = document.createElement("div");
    const rail = createRail(root, memoryStorage({ "pearlie.rail.collapsed": "1" }));
    expect(rail.collapsed).toBe(true);
    expect(root.dataset.rail).toBe("hidden");
  });

  it("works when storage throws", () => {
    const root = document.createElement("div");
    const bad = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    const rail = createRail(root, bad);
    expect(rail.collapsed).toBe(false);
    rail.toggle();
    expect(rail.collapsed).toBe(true);
    expect(root.dataset.rail).toBe("hidden");
  });
});
