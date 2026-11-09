// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { trapFocus } from "./focus";

describe("trapFocus", () => {
  let opener: HTMLButtonElement;
  let node: HTMLDivElement;
  let btn1: HTMLButtonElement;
  let btn2: HTMLButtonElement;

  beforeEach(() => {
    vi.useFakeTimers();
    opener = document.createElement("button");
    opener.textContent = "opener";
    document.body.appendChild(opener);

    node = document.createElement("div");
    btn1 = document.createElement("button");
    btn1.textContent = "first";
    btn2 = document.createElement("button");
    btn2.textContent = "second";
    node.appendChild(btn1);
    node.appendChild(btn2);
    document.body.appendChild(node);

    opener.focus();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.useRealTimers();
  });

  it("focuses the first button after trapFocus", () => {
    trapFocus(node);
    expect(document.activeElement).toBe(btn1);
  });

  it("Tab on last button moves focus to first and calls preventDefault", () => {
    trapFocus(node);
    btn2.focus();
    const e = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    btn2.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(btn1);
  });

  it("Shift+Tab on first button moves focus to last", () => {
    trapFocus(node);
    btn1.focus();
    const e = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    btn1.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(btn2);
  });

  it("destroy() returns focus to the opener", () => {
    const api = trapFocus(node);
    expect(document.activeElement).toBe(btn1);
    api.destroy();
    expect(document.activeElement).toBe(opener);
  });
});
