import { describe, it, expect } from "vitest";
import type { Settings } from "./settings";
import {
  SETTINGS_KEY,

  DEFAULT_SETTINGS,
  parseSettings,
  loadSettings,
  saveSettings,
} from "./settings";

describe("parseSettings", () => {
  it("returns defaults for null/null", () => {
    expect(parseSettings(null, null)).toEqual(DEFAULT_SETTINGS);
  });

  it("parses a valid JSON object", () => {
    const raw = JSON.stringify({ mode: "spread", fit: "width", dir: "rtl", zoom: 150 });
    expect(parseSettings(raw, null)).toEqual({ mode: "spread", fit: "width", dir: "rtl", zoom: 150 });
  });

  it("falls back per-field when fields are invalid", () => {
    const raw = JSON.stringify({ mode: "bogus", fit: "bogus", dir: "bogus", zoom: "nope" });
    expect(parseSettings(raw, null)).toEqual({ mode: null, fit: "both", dir: "ltr", zoom: 100 });
  });

  it("clamps zoom 10 to 50", () => {
    const raw = JSON.stringify({ zoom: 10 });
    expect(parseSettings(raw, null).zoom).toBe(50);
  });

  it("clamps zoom 999 to 300", () => {
    const raw = JSON.stringify({ zoom: 999 });
    expect(parseSettings(raw, null).zoom).toBe(300);
  });

  it("rounds zoom 120.4 to 120", () => {
    const raw = JSON.stringify({ zoom: 120.4 });
    expect(parseSettings(raw, null).zoom).toBe(120);
  });

  it("returns defaults for invalid JSON", () => {
    expect(parseSettings("not json{", null)).toEqual(DEFAULT_SETTINGS);
  });

  it("migrates from old key: spread+rtl+height", () => {
    const oldRaw = JSON.stringify({ spread: true, rtl: true, fit: "height" });
    expect(parseSettings(null, oldRaw)).toEqual({ mode: "spread", fit: "height", dir: "rtl", zoom: 100 });
  });

  it("migrates from old key: non-spread width", () => {
    const oldRaw = JSON.stringify({ spread: false, rtl: false, fit: "width" });
    expect(parseSettings(null, oldRaw)).toEqual({ mode: "single", fit: "width", dir: "ltr", zoom: 100 });
  });

  it("new key wins over old key", () => {
    const raw = JSON.stringify({ mode: "scroll", fit: "actual", dir: "ltr", zoom: 200 });
    const oldRaw = JSON.stringify({ spread: true, rtl: true, fit: "height" });
    expect(parseSettings(raw, oldRaw)).toEqual({ mode: "scroll", fit: "actual", dir: "ltr", zoom: 200 });
  });
});

describe("loadSettings", () => {
  it("returns defaults when storage getItem throws", () => {
    const fakeStorage: Pick<Storage, "getItem"> = {
      getItem: () => {
        throw new Error("storage unavailable");
      },
    };
    expect(loadSettings(fakeStorage)).toEqual(DEFAULT_SETTINGS);
  });
});

describe("saveSettings", () => {
  it("writes JSON under SETTINGS_KEY", () => {
    const items: Record<string, string> = {};
    const fakeStorage: Pick<Storage, "setItem"> = {
      setItem: (key, value) => {
        items[key] = value;
      },
    };
    const s: Settings = { mode: "spread", fit: "width", dir: "rtl", zoom: 200 };
    saveSettings(s, fakeStorage);
    expect(items[SETTINGS_KEY]).toBe(JSON.stringify(s));
  });

  it("swallows a throwing setItem", () => {
    const fakeStorage: Pick<Storage, "setItem"> = {
      setItem: () => {
        throw new Error("quota exceeded");
      },
    };
    expect(() => saveSettings(DEFAULT_SETTINGS, fakeStorage)).not.toThrow();
  });
});
