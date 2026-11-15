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

  it("setWidth clamps to 72-240, saves and sets --rail-w", () => {
    const root = document.createElement("div");
    const storage = memoryStorage();
    const rail = createRail(root, storage);
    rail.setWidth(150);
    expect(rail.width).toBe(150);
    expect(rail.px).toBe(150);
    expect(root.style.getPropertyValue("--rail-w")).toBe("150px");
    expect(storage.data["pearlie.rail.width"]).toBe("150");
    rail.setWidth(900);
    expect(rail.width).toBe(240);
    rail.setWidth(10);
    expect(rail.width).toBe(72);
    expect(root.style.getPropertyValue("--rail-w")).toBe("");
  });

  it("resetWidth returns to 72", () => {
    const root = document.createElement("div");
    const storage = memoryStorage();
    const rail = createRail(root, storage);
    rail.setWidth(200);
    rail.resetWidth();
    expect(rail.width).toBe(72);
    expect(root.style.getPropertyValue("--rail-w")).toBe("");
    expect(storage.data["pearlie.rail.width"]).toBe("72");
  });

  it("restores the saved width and ignores bad values", () => {
    const root = document.createElement("div");
    const rail = createRail(root, memoryStorage({ "pearlie.rail.width": "180" }));
    expect(rail.width).toBe(180);
    expect(root.style.getPropertyValue("--rail-w")).toBe("180px");
    const bad = createRail(document.createElement("div"), memoryStorage({ "pearlie.rail.width": "abc" }));
    expect(bad.width).toBe(72);
  });

  it("collapsed rail uses 0 px and keeps the width choice", () => {
    const root = document.createElement("div");
    const rail = createRail(root, memoryStorage({ "pearlie.rail.width": "160" }));
    rail.toggle();
    expect(rail.px).toBe(0);
    expect(rail.width).toBe(160);
    expect(root.style.getPropertyValue("--rail-w")).toBe("");
    rail.toggle();
    expect(rail.px).toBe(160);
    expect(root.style.getPropertyValue("--rail-w")).toBe("160px");
  });
});
