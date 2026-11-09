// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, screen, fireEvent } from "@testing-library/svelte";
import PagerComponent from "./Pager.svelte";

afterEach(() => {
  cleanup();
});

function baseProps() {
  return {
    page: 3,
    pages: 10,
    hasNext: true,
    perPage: 60,
    shown: 60,
    total: 600,
    stats: null,
    onpage: vi.fn(),
  };
}

describe("PagerComponent", () => {
  it("full form: navigation buttons and page combobox", () => {
    const props = baseProps();
    render(PagerComponent, props);

    const first = screen.getByRole("button", { name: "First page" });
    const prev = screen.getByRole("button", { name: "Previous page" });
    const next = screen.getByRole("button", { name: "Next page" });
    const last = screen.getByRole("button", { name: "Last page" });
    expect(first).not.toBeNull();
    expect(prev).not.toBeNull();
    expect(next).not.toBeNull();
    expect(last).not.toBeNull();

    const select = screen.getByRole("combobox", { name: "Page" }) as HTMLSelectElement;
    expect(select.value).toBe("3");

    fireEvent.click(next);
    expect(props.onpage).toHaveBeenCalledWith(4);

    fireEvent.click(prev);
    expect(props.onpage).toHaveBeenCalledWith(2);

    fireEvent.click(first);
    expect(props.onpage).toHaveBeenCalledWith(1);

    fireEvent.click(last);
    expect(props.onpage).toHaveBeenCalledWith(10);
  });

  it("page 1: First and Previous disabled; page 10: Next and Last disabled", () => {
    const onpage = vi.fn();

    const { unmount } = render(PagerComponent, {
      ...baseProps(),
      page: 1,
      hasNext: true,
      onpage,
    });

    const first = screen.getByRole("button", { name: "First page" }) as HTMLButtonElement;
    const prev = screen.getByRole("button", { name: "Previous page" }) as HTMLButtonElement;
    expect(first.disabled).toBe(true);
    expect(prev.disabled).toBe(true);

    unmount();

    render(PagerComponent, {
      ...baseProps(),
      page: 10,
      hasNext: false,
      onpage,
    });

    const next = screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement;
    const last = screen.getByRole("button", { name: "Last page" }) as HTMLButtonElement;
    expect(next.disabled).toBe(true);
    expect(last.disabled).toBe(true);
  });

  it("changing Page select to 7 calls onpage(7)", () => {
    const props = baseProps();
    render(PagerComponent, props);

    const select = screen.getByRole("combobox", { name: "Page" }) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "7" } });
    expect(props.onpage).toHaveBeenCalledWith(7);
  });

  it("reduced form: no Last button, no combobox, Page 3 text, Next toggle", () => {
    const { unmount } = render(PagerComponent, {
      page: 3,
      pages: null,
      hasNext: true,
      perPage: 60,
      shown: 60,
      total: null,
      stats: null,
      onpage: vi.fn(),
    });

    expect(screen.queryByRole("button", { name: "Last page" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Page" })).toBeNull();
    expect(screen.getByText("Page 3")).not.toBeNull();
    const next = screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement;
    expect(next.disabled).toBe(false);

    unmount();

    render(PagerComponent, {
      page: 3,
      pages: null,
      hasNext: false,
      perPage: 60,
      shown: 60,
      total: null,
      stats: null,
      onpage: vi.fn(),
    });

    const next2 = screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement;
    expect(next2.disabled).toBe(true);
  });

  it("range text: 121-180 of 600 with base props", () => {
    render(PagerComponent, baseProps());
    expect(screen.getByText("121-180 of 600")).not.toBeNull();
  });

  it("pages > 200: textbox, Enter commits valid, blur reverts invalid", async () => {
    const onpage = vi.fn();
    render(PagerComponent, {
      ...baseProps(),
      pages: 300,
      hasNext: true,
      total: 18000,
      onpage,
    });

    const input = screen.getByRole("textbox", { name: "Page" }) as HTMLInputElement;
    expect(input).not.toBeNull();

    await fireEvent.input(input, { target: { value: "250" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onpage).toHaveBeenCalledWith(250);

    await fireEvent.input(input, { target: { value: "999" } });
    await fireEvent.blur(input);
    expect(onpage).not.toHaveBeenCalledWith(999);
    expect(input.value).toBe("3");
  });
});
