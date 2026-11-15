// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import Nav from "./Nav.svelte";
import { rail } from "../stores/rail.svelte";

describe("Nav rail", () => {
  afterEach(() => {
    cleanup();
    delete document.documentElement.dataset.rail;
    document.documentElement.style.removeProperty("--rail-w");
    void rail?.resetWidth();
  });

  it("hides with the toggle and shows the reopen chevron", async () => {
    render(Nav, { current: "home", onnavigate: () => {} });
    expect(screen.queryByRole("button", { name: "Show navigation" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Hide navigation" }));
    expect(document.documentElement.dataset.rail).toBe("hidden");
    const reopen = screen.getByRole("button", { name: "Show navigation" });
    await fireEvent.click(reopen);
    expect(document.documentElement.dataset.rail).toBeUndefined();
  });

  it("renders the resize handle on the rail only", () => {
    render(Nav, { current: "home", onnavigate: () => {} });
    expect(screen.getByRole("separator", { name: /Resize navigation/ })).toBeTruthy();
    cleanup();
    render(Nav, { current: "home", onnavigate: () => {}, variant: "bar" });
    expect(screen.queryByRole("separator")).toBeNull();
  });

  it("dragging the handle sets the width, double-click resets", async () => {
    render(Nav, { current: "home", onnavigate: () => {} });
    const handle = screen.getByRole("separator", { name: /Resize navigation/ });
    await fireEvent.pointerDown(handle, { clientX: 72, button: 0, pointerId: 1 });
    await fireEvent.pointerMove(handle, { clientX: 180, pointerId: 1 });
    expect(rail?.width).toBe(180);
    expect(document.documentElement.style.getPropertyValue("--rail-w")).toBe("180px");
    await fireEvent.pointerUp(handle, { pointerId: 1 });
    await fireEvent.dblClick(handle);
    expect(rail?.width).toBe(72);
    expect(document.documentElement.style.getPropertyValue("--rail-w")).toBe("");
  });
});
