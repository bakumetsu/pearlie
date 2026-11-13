// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, screen, fireEvent } from "@testing-library/svelte";
import ViewBar from "./ViewBar.svelte";
import type { Mode } from "./layout";

function props() {
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

afterEach(cleanup);

describe("ViewBar invalid custom per-page", () => {
  it("Enter with 999 flags the field, keeps it open, does not call onperpage", async () => {
    const p = props();
    render(ViewBar, p);
    await fireEvent.change(screen.getByRole("combobox", { name: "Per page" }), { target: { value: "custom" } });
    const input = screen.getByRole("textbox", { name: "Custom per page" }) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "999" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(p.onperpage).not.toHaveBeenCalled();
    const again = screen.getByRole("textbox", { name: "Custom per page" });
    expect(again.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("alert").textContent).toContain("1");
    expect(screen.getByRole("alert").textContent).toContain("200");
  });

  it("typing again clears the error", async () => {
    render(ViewBar, props());
    await fireEvent.change(screen.getByRole("combobox", { name: "Per page" }), { target: { value: "custom" } });
    const input = screen.getByRole("textbox", { name: "Custom per page" }) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "abc" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.queryByRole("alert")).not.toBeNull();
    await fireEvent.input(input, { target: { value: "12" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
