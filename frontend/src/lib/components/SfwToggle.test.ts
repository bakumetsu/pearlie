// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import SfwToggle from "./SfwToggle.svelte";
import { sfw } from "../stores/sfw.svelte";

beforeEach(() => {
  sfw?.set(false);
});

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.sfw;
});

describe("SfwToggle", () => {
  it("starts with aria-pressed false and correct class", () => {
    render(SfwToggle);
    const btn = screen.getByRole("button", { name: "Hide media (SFW mode)" });
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    expect(btn.classList.contains("sfw-toggle")).toBe(true);
  });

  it("toggles on: aria-pressed true, data-sfw on, icon swaps to eye-off (4 paths)", async () => {
    render(SfwToggle);
    const btn = screen.getByRole("button", { name: "Hide media (SFW mode)" });

    // Initial: eye icon → 2 paths
    let paths = btn.querySelectorAll("svg path");
    expect(paths.length).toBe(2);

    await fireEvent.click(btn);

    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(document.documentElement.dataset.sfw).toBe("on");

    // Now: eye-off icon → 4 paths
    paths = btn.querySelectorAll("svg path");
    expect(paths.length).toBe(4);
  });

  it("toggles off on second click", async () => {
    render(SfwToggle);
    const btn = screen.getByRole("button", { name: "Hide media (SFW mode)" });

    await fireEvent.click(btn);
    expect(btn.getAttribute("aria-pressed")).toBe("true");

    await fireEvent.click(btn);
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    expect(document.documentElement.dataset.sfw).toBeUndefined();
  });
});
