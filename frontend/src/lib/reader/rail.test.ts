import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import { describe, it, expect, vi, afterEach } from "vitest";
import { tick } from "svelte";

import Rail from "./Rail.svelte";
import type { Fit, Mode } from "./pages";

type RailProps = import("svelte").ComponentProps<typeof Rail>;

afterEach(cleanup);

function makeProps(overrides: Partial<RailProps> = {}): RailProps {
  return {
    fit: "both" as Fit,
    mode: "single" as Mode,
    fullscreen: false,
    settingsOpen: false,
    zoom: 100,
    hidden: false,
    onback: vi.fn(),
    onsettings: vi.fn(),
    onfit: vi.fn(),
    onmode: vi.fn(),
    onfullscreen: vi.fn(),
    onhelp: vi.fn(),
    onzoomin: vi.fn(),
    onzoomout: vi.fn(),
    onzoomreset: vi.fn(),
    ...overrides,
  };
}

describe("Rail", () => {
  it("Zoom button has aria-expanded false and #rail-zoom has no open class initially", () => {
    render(Rail, makeProps());

    const zoomBtn = screen.getByRole("button", { name: "Zoom" });
    expect(zoomBtn.getAttribute("aria-expanded")).toBe("false");

    const zoomPanel = document.getElementById("rail-zoom");
    expect(zoomPanel!.classList.contains("open")).toBe(false);
  });

  it("clicking Zoom opens the panel; clicking again collapses", async () => {
    render(Rail, makeProps());

    const zoomBtn = screen.getByRole("button", { name: "Zoom" });
    const zoomPanel = document.getElementById("rail-zoom")!;

    await fireEvent.click(zoomBtn);
    await tick();
    expect(zoomBtn.getAttribute("aria-expanded")).toBe("true");
    expect(zoomPanel.classList.contains("open")).toBe(true);

    await fireEvent.click(zoomBtn);
    await tick();
    expect(zoomBtn.getAttribute("aria-expanded")).toBe("false");
    expect(zoomPanel.classList.contains("open")).toBe(false);
  });

  it("Zoom in / Zoom out / Reset zoom call their handlers; reset text contains current zoom", async () => {
    const onzoomin = vi.fn();
    const onzoomout = vi.fn();
    const onzoomreset = vi.fn();
    render(Rail, makeProps({ onzoomin, onzoomout, onzoomreset }));

    await fireEvent.click(screen.getByRole("button", { name: "Zoom" }));
    await tick();

    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    const zoomOut = screen.getByRole("button", { name: "Zoom out" });
    const reset = screen.getByRole("button", { name: "Reset zoom" });

    await fireEvent.click(zoomIn);
    await fireEvent.click(zoomOut);
    await fireEvent.click(reset);
    await tick();

    expect(onzoomin).toHaveBeenCalledTimes(1);
    expect(onzoomout).toHaveBeenCalledTimes(1);
    expect(onzoomreset).toHaveBeenCalledTimes(1);
    expect(reset.textContent).toContain("100");
  });

  it("Zoom in is disabled at zoom 300; Zoom out disabled at zoom 50", async () => {
    const { unmount } = render(Rail, makeProps({ zoom: 300 }));
    await fireEvent.click(screen.getByRole("button", { name: "Zoom" }));
    await tick();
    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    expect((zoomIn as HTMLButtonElement).disabled).toBe(true);
    unmount();

    render(Rail, makeProps({ zoom: 50 }));
    await fireEvent.click(screen.getByRole("button", { name: "Zoom" }));
    await tick();
    const zoomOut = screen.getByRole("button", { name: "Zoom out" });
    expect((zoomOut as HTMLButtonElement).disabled).toBe(true);
  });

  it("Escape keydown on Zoom in button while open collapses the panel", async () => {
    render(Rail, makeProps());

    const zoomBtn = screen.getByRole("button", { name: "Zoom" });
    await fireEvent.click(zoomBtn);
    await tick();
    expect(zoomBtn.getAttribute("aria-expanded")).toBe("true");

    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    await fireEvent.keyDown(zoomIn, { key: "Escape" });
    await tick();

    expect(zoomBtn.getAttribute("aria-expanded")).toBe("false");
  });

  it("rerender with hidden true collapses the open panel", async () => {
    const { rerender } = render(Rail, makeProps());

    const zoomBtn = screen.getByRole("button", { name: "Zoom" });
    await fireEvent.click(zoomBtn);
    await tick();
    expect(zoomBtn.getAttribute("aria-expanded")).toBe("true");

    await rerender({ hidden: true });
    await tick();

    expect(zoomBtn.getAttribute("aria-expanded")).toBe("false");
  });
});
