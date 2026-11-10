// panelState tests
import { describe, it, expect, vi } from "vitest";
import { PANEL_KEY, savePanel, initialOpen } from "./panelState";

function makeStorage(values: Record<string, string> = {}) {
  return {
    getItem: vi.fn((key: string) => values[key] ?? null),
    setItem: vi.fn(),
  };
}

describe("panelState", () => {
  it("desktop width 1024 with no stored value => open", () => {
    const s = makeStorage();
    expect(initialOpen(1024, s)).toBe(true);
  });

  it("phone width 375 with no stored value => closed", () => {
    const s = makeStorage();
    expect(initialOpen(375, s)).toBe(false);
  });

  it("stored 'closed' at desktop 1024 => closed", () => {
    const s = makeStorage({ [PANEL_KEY]: "closed" });
    expect(initialOpen(1024, s)).toBe(false);
  });

  it("stored 'open' at phone 375 => open", () => {
    const s = makeStorage({ [PANEL_KEY]: "open" });
    expect(initialOpen(375, s)).toBe(true);
  });

  it("invalid stored value falls back to width default", () => {
    const s = makeStorage({ [PANEL_KEY]: "banana" });
    expect(initialOpen(1024, s)).toBe(true);
    expect(initialOpen(375, s)).toBe(false);
  });

  it("storage whose getItem throws still returns width default", () => {
    const s = makeStorage();
    s.getItem.mockImplementation(() => { throw new Error("blocked"); });
    expect(initialOpen(1024, s)).toBe(true);
    expect(initialOpen(375, s)).toBe(false);
  });

  it("savePanel does not throw when setItem throws", () => {
    const s = makeStorage();
    s.setItem.mockImplementation(() => { throw new Error("quota"); });
    expect(() => savePanel(true, s)).not.toThrow();
    expect(() => savePanel(false, s)).not.toThrow();
  });

  it("initialOpen never calls setItem", () => {
    const s = makeStorage({ [PANEL_KEY]: "open" });
    initialOpen(375, s);
    expect(s.setItem).toHaveBeenCalledTimes(0);
  });

  it("savePanel(false) writes 'closed'", () => {
    const s = makeStorage();
    savePanel(false, s);
    expect(s.setItem).toHaveBeenCalledWith(PANEL_KEY, "closed");
  });

  it("savePanel(true) writes 'open'", () => {
    const s = makeStorage();
    savePanel(true, s);
    expect(s.setItem).toHaveBeenCalledWith(PANEL_KEY, "open");
  });
});
