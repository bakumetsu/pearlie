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

  it("blur does not commit pending text", async () => {
    const onchange = vi.fn();
    const { container } = render(ChipField, { props: { chips: [], onchange } });
    const input = container.querySelector("input")!;
    await fireEvent.input(input, { target: { value: "cat" } });
    await fireEvent.blur(input);
    expect(onchange).not.toHaveBeenCalled();
    expect((input as HTMLInputElement).value).toBe("cat");
  });

  it("has correct padding in styles", () => {
    expect(src).toContain("padding: 2px 18px 2px var(--s-1)");
  });

  it("comma inside an open quote does not commit; Enter does", async () => {
    const onchange = vi.fn();
    const { container } = render(ChipField, { props: { chips: [], onchange } });
    const input = container.querySelector("input")!;
    await fireEvent.input(input, { target: { value: '"big, dragon' } });
    await fireEvent.keyDown(input, { key: "," });
    expect(onchange).not.toHaveBeenCalled();
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange.mock.calls[0][0][0].raw).toBe('title:"big, dragon"');
  });

  it("shows a title chip like a tag chip and removes it", async () => {
    const onchange = vi.fn();
    const chips = [{ raw: 'title:"big dragon"', exclude: false, scope: "title", value: "big dragon" }];
    const { container, getByLabelText } = render(ChipField, { props: { chips, onchange } });
    expect(container.querySelector(".chip")!.textContent).toContain("title:big dragon");
    await fireEvent.click(getByLabelText("Remove title big dragon"));
    expect(onchange).toHaveBeenCalledWith([]);
  });
});
