// WallOverlay tests
// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import WallOverlay from "./WallOverlay.svelte";
import type { Api, LibraryItem } from "../api/client";

afterEach(() => {
  cleanup();
});

function makeItems(): LibraryItem[] {
  return [
    { kind: "image", id: "a", title: "A", thumb_url: "/t/a", favorite: false, added_at: "2026-01-01" },
    { kind: "image", id: "b", title: "B", thumb_url: "/t/b", favorite: false, added_at: "2026-01-01" },
    { kind: "image", id: "c", title: "C", thumb_url: "/t/c", favorite: false, added_at: "2026-01-01" },
  ];
}

function makeGrid(over: Record<string, unknown> = {}) {
  return {
    items: makeItems(),
    page: 1,
    pages: 3,
    hasNext: true,
    status: "done",
    total: 7,
    stats: null,
    goTo: vi.fn(async () => {}),
    markCrossed: vi.fn(),
    removeById: vi.fn(() => null),
    restore: vi.fn(),
    updateById: vi.fn(() => true),
    ...over,
  };
}

function makeApi(over: Record<string, unknown> = {}): Api {
  const base = {
    getItem: vi.fn(
      async (_k: string, id: string) => ({
        kind: "image",
        id,
        title: id.toUpperCase(),
        thumb_url: "/t/" + id,
        full_url: "/f/" + id,
        favorite: false,
        added_at: "2026-01-01",
        file_name: id + ".jpg",
        tags: [],
        rating: 3,
      }),
    ),
    patchItem: vi.fn(async () => ({})),
  };
  return { ...base, ...over } as unknown as Api;
}

function makeToasts() {
  return { push: vi.fn(() => 1) };
}

function mount(over: Record<string, unknown> = {}) {
  const onstep = (over.onstep as ReturnType<typeof vi.fn>) ?? vi.fn();
  const onclose = (over.onclose as ReturnType<typeof vi.fn>) ?? vi.fn();
  const onpage = (over.onpage as ReturnType<typeof vi.fn>) ?? vi.fn();
  const grid = makeGrid((over.grid as Record<string, unknown>) ?? {});
  const result = render(WallOverlay, {
    id: (over.id as string) ?? "a",
    grid,
    perPage: (over.perPage as number) ?? 3,
    api: (over.api as Api) ?? makeApi(),
    toasts: (over.toasts as ReturnType<typeof makeToasts>) ?? makeToasts(),
    onstep,
    onclose,
    onpage,
  });
  return { ...result, onstep, onclose, onpage, grid };
}

describe("WallOverlay", () => {
  it("renders role dialog named 'Image viewer' with a Close button that has focus", () => {
    const { getByRole } = mount();
    const dialog = getByRole("dialog", { name: "Image viewer" });
    expect(dialog).toBeTruthy();
    const closeBtn = getByRole("button", { name: "Close" });
    expect(document.activeElement).toBe(closeBtn);
  });

  it("page label: select 'Page' with value '1', options text '1 / 3', '2 / 3', '3 / 3'; range text '1-3 of 7' visible; no First/Previous/Next/Last page buttons", () => {
    const { getByRole, getByLabelText, queryByRole } = mount();
    const select = getByLabelText("Page") as HTMLSelectElement;
    expect(select.value).toBe("1");
    const options = select.querySelectorAll("option");
    expect(options[0]?.textContent).toBe("1 / 3");
    expect(options[1]?.textContent).toBe("2 / 3");
    expect(options[2]?.textContent).toBe("3 / 3");
    expect((getByRole("dialog") as HTMLElement).textContent).toContain("1-3 of 7");
    expect(queryByRole("button", { name: "First page" })).toBeNull();
    expect(queryByRole("button", { name: "Previous page" })).toBeNull();
    expect(queryByRole("button", { name: "Next page" })).toBeNull();
    expect(queryByRole("button", { name: "Last page" })).toBeNull();
  });

  it("choosing page 2 in the select calls onpage(2)", () => {
    const onpage = vi.fn();
    const { getByLabelText } = mount({ onpage });
    const select = getByLabelText("Page") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "2" } });
    expect(onpage).toHaveBeenCalledWith(2);
  });

  it("chevron states reflect position and page edges", () => {
    // id "a" on page 1: prev disabled, next enabled
    let { getByRole } = mount({ id: "a" });
    expect((getByRole("button", { name: "Previous image" }) as HTMLButtonElement).disabled).toBe(true);
    expect((getByRole("button", { name: "Next image" }) as HTMLButtonElement).disabled).toBe(false);
    cleanup();

    // id "c" with hasNext true: next enabled (page edge crossing)
    ({ getByRole } = mount({ id: "c", grid: { hasNext: true } }));
    expect((getByRole("button", { name: "Next image" }) as HTMLButtonElement).disabled).toBe(false);
    cleanup();

    // id "c" with hasNext false, pages 1: next disabled
    ({ getByRole } = mount({ id: "c", grid: { hasNext: false, pages: 1 } }));
    expect((getByRole("button", { name: "Next image" }) as HTMLButtonElement).disabled).toBe(true);
    cleanup();

    // id "a" on page 2: prev enabled
    ({ getByRole } = mount({ id: "a", grid: { page: 2 } }));
    expect((getByRole("button", { name: "Previous image" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("clicking 'Next image' calls onstep('b')", async () => {
    const onstep = vi.fn();
    const { getByRole } = mount({ onstep });
    fireEvent.click(getByRole("button", { name: "Next image" }));
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
  });

  it("ArrowRight and 'l' call onstep('b'); ArrowLeft and 'j' with id 'b' call onstep('a')", async () => {
    // ArrowRight calls onstep('b')
    let onstep = vi.fn();
    let { container } = mount({ onstep });
    let dialog = container.querySelector(".layer")!;
    fireEvent.keyDown(dialog, { key: "ArrowRight" });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
    cleanup();

    // 'l' calls onstep('b')
    onstep = vi.fn();
    ({ container } = mount({ onstep }));
    dialog = container.querySelector(".layer")!;
    fireEvent.keyDown(dialog, { key: "l" });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
    cleanup();

    // ArrowLeft with id 'b' calls onstep('a')
    onstep = vi.fn();
    ({ container } = mount({ onstep, id: "b" }));
    dialog = container.querySelector(".layer")!;
    fireEvent.keyDown(dialog, { key: "ArrowLeft" });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("a"));
    cleanup();

    // 'j' with id 'b' calls onstep('a')
    onstep = vi.fn();
    ({ container } = mount({ onstep, id: "b" }));
    dialog = container.querySelector(".layer")!;
    fireEvent.keyDown(dialog, { key: "j" });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("a"));
    cleanup();
  });

  it("Escape calls onclose; ctrl+ArrowRight does not step; keydown on page select does not step or close", async () => {
    const onclose = vi.fn();
    const onstep = vi.fn();
    const { container } = mount({ onclose, onstep });
    const dialog = container.querySelector(".layer")!;

    // Escape calls onclose
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onclose).toHaveBeenCalledTimes(1);
    onclose.mockClear();

    // ctrl+ArrowRight does not step
    fireEvent.keyDown(dialog, { key: "ArrowRight", ctrlKey: true });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
    cleanup();

    // keydown on page select does not step or close
    const { getByLabelText: getSel } = mount({ onclose, onstep });
    const select = getSel("Page");
    fireEvent.keyDown(select, { key: "Escape" });
    fireEvent.keyDown(select, { key: "ArrowRight" });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
    expect(onclose).not.toHaveBeenCalled();
  });

  it("Escape while zoomed only un-zooms; second Escape closes", async () => {
    const onclose = vi.fn();
    const { getByRole } = mount({ onclose });

    // wait for ImageStage to render its "Actual size" button
    const actualSize = await waitFor(() =>
      getByRole("button", { name: "Actual size" }),
    );
    fireEvent.click(actualSize);

    // first Escape un-zooms, does not close
    const dialog = getByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onclose).not.toHaveBeenCalled();

    // second Escape closes
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onclose).toHaveBeenCalledTimes(1);
  });

  it("shows 'a.jpg' (file_name) as text after the detail loads", async () => {
    const { findByText } = mount();
    const el = await findByText("a.jpg");
    expect(el).toBeTruthy();
  });

  it("Tab on the last focusable wraps to the first (Close button)", async () => {
    const { getByRole, container } = mount();
    const dialog = container.querySelector(".layer")!;

    // wait for ImageStage button so the last focusable is deterministic
    await waitFor(() => {
      expect(dialog.querySelector('button[aria-label="Actual size"]')).toBeTruthy();
    });

    // compute last focusable the same way the component does
    const sel =
      'button:not([disabled]), select, input, a[href], [tabindex]:not([tabindex="-1"])';
    const focusable = dialog.querySelectorAll(sel);
    expect(focusable.length).toBeGreaterThan(0);
    const last = focusable[focusable.length - 1] as HTMLElement;
    last.focus();

    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(getByRole("button", { name: "Close" }));
  });

  it("clicking the dialog element itself calls onclose", () => {
    const onclose = vi.fn();
    const { container } = mount({ onclose });
    const dialog = container.querySelector(".layer")!;
    fireEvent.click(dialog);
    expect(onclose).toHaveBeenCalledTimes(1);
  });

  it("zoom button and z key share one state", async () => {
    const { getByRole, container } = mount();
    const dialog = container.querySelector(".layer")!;

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    const zoomBtn = getByRole("button", { name: "Zoom" });
    expect(zoomBtn.getAttribute("aria-pressed")).toBe("false");

    await fireEvent.keyDown(dialog, { key: "z" });
    expect(zoomBtn.getAttribute("aria-pressed")).toBe("true");

    await fireEvent.click(zoomBtn);
    expect(zoomBtn.getAttribute("aria-pressed")).toBe("false");
  });

  it("Escape un-zooms first; second Escape closes", async () => {
    const onclose = vi.fn();
    const { getByRole, container } = mount({ onclose });
    const dialog = container.querySelector(".layer")!;

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    const zoomBtn = getByRole("button", { name: "Zoom" });

    await fireEvent.keyDown(dialog, { key: "z" });
    expect(zoomBtn.getAttribute("aria-pressed")).toBe("true");

    await fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onclose).not.toHaveBeenCalled();
    expect(zoomBtn.getAttribute("aria-pressed")).toBe("false");

    await fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onclose).toHaveBeenCalledTimes(1);
  });

  it("key 4 calls api.patchItem with rating:4; pressing same value again clears with rating:null", async () => {
    const patchItem = vi.fn(async () => ({}));
    const { getByRole, container } = mount({ api: makeApi({ patchItem }) });
    const dialog = container.querySelector(".layer")!;

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    await fireEvent.keyDown(dialog, { key: "4" });
    await waitFor(() => {
      expect(patchItem).toHaveBeenCalledWith("images", "a", { rating: 4 });
    });

    await waitFor(() => {
      const radio4 = getByRole("radio", { name: "Rating 4 of 5" });
      expect(radio4.getAttribute("aria-checked")).toBe("true");
    });

    await fireEvent.keyDown(dialog, { key: "4" });
    await waitFor(() => {
      expect(patchItem).toHaveBeenCalledWith("images", "a", { rating: null });
    });
  });

  it("patchItem rejects: rating rolls back and error toast shown", async () => {
    const patchItem = vi.fn(async () => { throw new Error("fail"); });
    const toasts = makeToasts();
    const { getByRole, container } = mount({ api: makeApi({ patchItem }), toasts });
    const dialog = container.querySelector(".layer")!;

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    await fireEvent.keyDown(dialog, { key: "4" });

    await waitFor(() => {
      expect(patchItem).toHaveBeenCalledWith("images", "a", { rating: 4 });
    });

    await waitFor(() => {
      const radio3 = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio3.getAttribute("aria-checked")).toBe("true");
    });

    expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Could not save the rating. Try again." });
  });

  it("before detail loads, key 4 and star click do not call patchItem", async () => {
    const patchItem = vi.fn();
    const api = {
      ...makeApi({ patchItem }),
      getItem: vi.fn(() => new Promise(() => {})),
    } as unknown as Api;
    const { queryByRole, container } = mount({ api });
    const dialog = container.querySelector(".layer")!;

    await fireEvent.keyDown(dialog, { key: "4" });

    const star = queryByRole("radio", { name: "Rating 4 of 5" });
    if (star) {
      await fireEvent.click(star);
    }

    expect(patchItem).not.toHaveBeenCalled();
  });

  it("keys 1-5 and z ignored while focus is in the page select", async () => {
    const patchItem = vi.fn(async () => ({}));
    const { getByLabelText, getByRole } = mount({ api: makeApi({ patchItem }) });

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    const select = getByLabelText("Page");
    await fireEvent.keyDown(select, { key: "4" });
    await fireEvent.keyDown(select, { key: "z" });

    expect(getByRole("button", { name: "Zoom" }).getAttribute("aria-pressed")).toBe("false");
    expect(patchItem).not.toHaveBeenCalled();
  });

  it("Details link has href '/item/images/a'", async () => {
    const { getByRole } = mount();

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    const link = getByRole("link", { name: "Details" });
    expect(link.getAttribute("href")).toBe("/item/images/a");
  });

  it("grid.updateById called with ('image:a', {rating:4}) after rating succeeds", async () => {
    const patchItem = vi.fn(async () => ({}));
    const { getByRole, container, grid } = mount({ api: makeApi({ patchItem }) });
    const dialog = container.querySelector(".layer")!;

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    await fireEvent.keyDown(dialog, { key: "4" });

    await waitFor(() => {
      expect(grid.updateById).toHaveBeenCalledWith("image:a", { rating: 4 });
    });
  });
});
