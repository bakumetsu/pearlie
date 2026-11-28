// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { createRawSnippet } from "svelte";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import RadioGroup from "./RadioGroup.svelte";
import Switch from "./Switch.svelte";
import Button from "./Button.svelte";
import ChipField from "./ChipField.svelte";
import Tabs from "./Tabs.svelte";
import DropdownMenu from "./DropdownMenu.svelte";
import AlertDialog from "./AlertDialog.svelte";
import Toaster from "./Toaster.svelte";
import { undoToast } from "./undoToast";
import { toasts } from "../stores/toasts.svelte";

afterEach(() => {
  cleanup();
  toasts.dismiss();
});

const text = (s: string) => createRawSnippet(() => ({ render: () => `<span>${s}</span>` }));

describe("RadioGroup", () => {
  it("arrow keys move and select, wrapping", async () => {
    render(RadioGroup, { label: "R", value: "a", options: [{ value: "a", label: "A" }, { value: "b", label: "B" }] });
    const a = screen.getByRole("radio", { name: "A" });
    a.focus();
    await fireEvent.keyDown(a, { key: "ArrowDown" });
    expect(screen.getByRole("radio", { name: "B" }).getAttribute("aria-checked")).toBe("true");
    await fireEvent.keyDown(screen.getByRole("radio", { name: "B" }), { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "A" }).getAttribute("aria-checked")).toBe("true");
  });
});

describe("Switch", () => {
  it("is role=switch with aria-checked and calls onclick", async () => {
    const onclick = vi.fn();
    render(Switch, { checked: true, label: "S", onclick });
    const sw = screen.getByRole("switch", { name: "S" });
    expect(sw.getAttribute("aria-checked")).toBe("true");
    await fireEvent.click(sw);
    expect(onclick).toHaveBeenCalledOnce();
  });
});

describe("Button", () => {
  it("default size has the 44 px classes", () => {
    render(Button, { children: text("Go") });
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("h-11");
    expect(cls).toContain("min-w-11");
  });
});

describe("ChipField", () => {
  it("Enter commits text, Backspace on empty removes the last chip, Enter on empty submits", async () => {
    let chips: { raw: string }[] = [];
    const onchange = vi.fn((c) => (chips = c));
    const onsubmit = vi.fn();
    const { rerender } = render(ChipField, { chips: [], onchange, onsubmit });
    const input = screen.getByRole("textbox");
    await fireEvent.input(input, { target: { value: "cat" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onchange).toHaveBeenCalledOnce();
    expect(chips.length).toBe(1);
    await rerender({ chips: chips as never, onchange, onsubmit });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onsubmit).toHaveBeenCalledOnce();
    await fireEvent.keyDown(input, { key: "Backspace" });
    expect(onchange).toHaveBeenLastCalledWith([]);
  });
});

describe("Tabs", () => {
  it("renders tabs with the active one selected", () => {
    render(Tabs, { label: "T", value: "one", tabs: [{ value: "one", label: "One" }, { value: "two", label: "Two" }] });
    expect(screen.getByRole("tab", { name: "One" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Two" }).getAttribute("aria-selected")).toBe("false");
  });
});

describe("DropdownMenu", () => {
  it("trigger is a menu button", () => {
    render(DropdownMenu, {
      label: "Sort",
      value: "a",
      options: [{ value: "a", label: "A" }, { value: "b", label: "B" }],
      trigger: createRawSnippet<[string]>((cur) => ({ render: () => `<span>${cur()}</span>` })),
    });
    const btn = screen.getByRole("button", { name: "Sort" });
    expect(btn.getAttribute("aria-haspopup")).toBe("menu");
    expect(btn.className).toContain("h-11");
  });
});

describe("AlertDialog", () => {
  it("shows an alertdialog; confirm calls onconfirm", async () => {
    const onconfirm = vi.fn();
    render(AlertDialog, { open: true, title: "Delete?", description: "d", confirmLabel: "Delete", onconfirm });
    expect(await screen.findByRole("alertdialog")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onconfirm).toHaveBeenCalledOnce();
  });
});

describe("Toaster + undoToast", () => {
  it("shows an 8 s Undo toast and runs the undo action", async () => {
    const onundo = vi.fn();
    render(Toaster);
    undoToast("Moved", onundo);
    expect(toasts.current?.durationMs).toBe(8000);
    await fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(onundo).toHaveBeenCalledOnce();
  });
});
