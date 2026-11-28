import { describe, it, expect } from "vitest";
import { createTheme, THEME_KEY } from "./theme";
import { THEMES, findTheme } from "./themes";

function memory(init: Record<string, string> = {}) {
  const data = { ...init };
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => { data[k] = v; },
  };
}

describe("theme list", () => {
  it("ships dark first and light, each with swatch vars", () => {
    expect(THEMES.map((t) => t.id)).toEqual(["dark", "light"]);
    for (const t of THEMES) expect(Object.keys(t.vars)).toEqual(["background", "foreground", "primary"]);
  });
  it("falls back to dark for an unknown or empty id", () => {
    expect(findTheme("nope").id).toBe("dark");
    expect(findTheme(null).id).toBe("dark");
  });
});

describe("createTheme", () => {
  it("applies dark with no stored choice", () => {
    const root = document.createElement("html");
    createTheme(root, memory());
    expect(root.dataset.theme).toBe("dark");
    expect(root.dataset.mode).toBe("dark");
  });
  it("applies the stored theme at boot", () => {
    const root = document.createElement("html");
    createTheme(root, memory({ [THEME_KEY]: "light" }));
    expect(root.dataset.theme).toBe("light");
    expect(root.dataset.mode).toBe("light");
  });
  it("set() applies and stores the choice", () => {
    const root = document.createElement("html");
    const store = memory();
    const t = createTheme(root, store);
    t.set("light");
    expect(root.dataset.theme).toBe("light");
    expect(t.current.id).toBe("light");
    expect(store.data[THEME_KEY]).toBe("light");
  });
  it("survives blocked storage", () => {
    const root = document.createElement("html");
    const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    const t = createTheme(root, blocked);
    t.set("light");
    expect(root.dataset.theme).toBe("light");
  });
});
