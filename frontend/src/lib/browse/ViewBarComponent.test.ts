// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, screen, fireEvent } from "@testing-library/svelte";
import ViewBarComponent from "./ViewBar.svelte";
import type { Mode } from "./layout";

function baseProps() {
  return {
    mode: "grid" as Mode,
    modes: ["grid", "wall", "masonry", "list"] as Mode[],
    perPage: 60,
    zoom: 3,
    options: [20, 40, 60, 100, 200],
    max: 200,
    onmode: vi.fn(),
    onperpage: vi.fn(),
    onzoom: vi.fn(),
    onzoompreview: vi.fn(),
  };
}

afterEach(() => {
  cleanup();
  window.innerWidth = 1024;
});

describe("ViewBarComponent", () => {
  it("wide: combobox, four mode buttons, zoom slider", () => {
    const props = baseProps();
    render(ViewBarComponent, props);

    const select = screen.getByRole("combobox", { name: "Per page" }) as HTMLSelectElement;
    expect(select.value).toBe("60");

    const grid = screen.getByRole("button", { name: "Grid" }) as HTMLButtonElement;
    const wall = screen.getByRole("button", { name: "Wall" }) as HTMLButtonElement;
    const masonry = screen.getByRole("button", { name: "Masonry" }) as HTMLButtonElement;
    const list = screen.getByRole("button", { name: "List" }) as HTMLButtonElement;
    expect(grid.getAttribute("aria-pressed")).toBe("true");
    expect(wall.getAttribute("aria-pressed")).toBe("false");
    expect(masonry.getAttribute("aria-pressed")).toBe("false");
    expect(list.getAttribute("aria-pressed")).toBe("false");

    const slider = screen.getByRole("slider", { name: "Zoom" });
    expect(slider).not.toBeNull();
  });

  it("clicking Wall calls onmode(\"wall\")", async () => {
    const props = baseProps();
    render(ViewBarComponent, props);

    const wall = screen.getByRole("button", { name: "Wall" });
    await fireEvent.click(wall);
    expect(props.onmode).toHaveBeenCalledWith("wall");
  });

  it("choosing 100 in Per page calls onperpage(100)", async () => {
    const props = baseProps();
    render(ViewBarComponent, props);

    const select = screen.getByRole("combobox", { name: "Per page" });
    await fireEvent.change(select, { target: { value: "100" } });
    expect(props.onperpage).toHaveBeenCalledWith(100);
  });

  it("choosing custom shows textbox; 150 commits, 999 rejected", async () => {
    const props = baseProps();
    render(ViewBarComponent, props);

    const select = screen.getByRole("combobox", { name: "Per page" });
    await fireEvent.change(select, { target: { value: "custom" } });

    let input = screen.getByRole("textbox", { name: "Custom per page" }) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "150" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(props.onperpage).toHaveBeenCalledWith(150);

    await fireEvent.change(select, { target: { value: "custom" } });
    input = screen.getByRole("textbox", { name: "Custom per page" }) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "999" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(props.onperpage).not.toHaveBeenCalledWith(999);
  });

  it("non-preset perPage 75 appears as option and is selected", () => {
    render(ViewBarComponent, { ...baseProps(), perPage: 75 });

    const select = screen.getByRole("combobox", { name: "Per page" }) as HTMLSelectElement;
    expect(select.value).toBe("75");

    const options = screen.getAllByRole("option");
    const values = options.map((o) => o.textContent);
    expect(values).toContain("75");
  });

  it("zoom: input calls onzoompreview, change calls onzoom", async () => {
    const props = baseProps();
    render(ViewBarComponent, props);

    const slider = screen.getByRole("slider", { name: "Zoom" }) as HTMLInputElement;
    await fireEvent.input(slider, { target: { value: "4" } });
    expect(props.onzoompreview).toHaveBeenCalledWith(4);

    await fireEvent.change(slider, { target: { value: "4" } });
    expect(props.onzoom).toHaveBeenCalledWith(4);
  });

  it("modes [wall, list] renders exactly two mode buttons: Wall and List", () => {
    render(ViewBarComponent, { ...baseProps(), modes: ["wall", "list"] as Mode[] });

    expect(screen.getByRole("button", { name: "Wall" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "List" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Grid" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Masonry" })).toBeNull();
  });

  it("modes [grid, list] renders exactly Grid and List", () => {
    render(ViewBarComponent, { ...baseProps(), modes: ["grid", "list"] as Mode[] });

    expect(screen.getByRole("button", { name: "Grid" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "List" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Wall" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Masonry" })).toBeNull();
  });

  it("clicking an offered button calls onmode with that mode", async () => {
    const props = { ...baseProps(), modes: ["wall", "list"] as Mode[] };
    render(ViewBarComponent, props);

    const listBtn = screen.getByRole("button", { name: "List" });
    await fireEvent.click(listBtn);
    expect(props.onmode).toHaveBeenCalledWith("list");
  });

  it("phone: View button opens sheet dialog with controls and Done", async () => {
    window.innerWidth = 500;
    window.dispatchEvent(new Event("resize"));
    const props = baseProps();
    render(ViewBarComponent, props);

    expect(screen.queryByRole("combobox", { name: "Per page" })).toBeNull();
    const viewBtn = screen.getByRole("button", { name: "View" });
    expect(viewBtn).not.toBeNull();

    await fireEvent.click(viewBtn);

    const dialog = screen.getByRole("dialog", { name: "View settings" });
    expect(dialog).not.toBeNull();
    expect(screen.getByRole("combobox", { name: "Per page" })).not.toBeNull();
    const done = screen.getByRole("button", { name: "Done" });
    expect(done).not.toBeNull();

    await fireEvent.click(done);
    expect(screen.queryByRole("dialog", { name: "View settings" })).toBeNull();
  });
});
