// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import ChipField from "./ChipField.svelte";
import src from "./ChipField.svelte?raw";

afterEach(cleanup);

describe("ChipField", () => {
  it("Space keyDown does not commit", async () => {
    const onchange = vi.fn();
    const { container } = render(ChipField, { props: { chips: [], onchange } });
    const input = container.querySelector("input")!;
    await fireEvent.input(input, { target: { value: "cat" } });
    await fireEvent.keyDown(input, { key: " " });
    expect(onchange).not.toHaveBeenCalled();
  });

  it("Enter keyDown commits once", async () => {
    const onchange = vi.fn();
    const { container } = render(ChipField, { props: { chips: [], onchange } });
    const input = container.querySelector("input")!;
    await fireEvent.input(input, { target: { value: "cat" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onchange).toHaveBeenCalledTimes(1);
  });

  it("comma keyDown commits", async () => {
    const onchange = vi.fn();
    const { container } = render(ChipField, { props: { chips: [], onchange } });
    const input = container.querySelector("input")!;
    await fireEvent.input(input, { target: { value: "cat" } });
    await fireEvent.keyDown(input, { key: "," });
    expect(onchange).toHaveBeenCalled();
  });

  it("has correct padding in styles", () => {
    expect(src).toContain("padding: 2px 18px 2px var(--s-1)");
  });
});
