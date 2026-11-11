// WallOverlay tests
// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import WallOverlay from "./WallOverlay.svelte";
import type { Api, LibraryItem } from "../api/client";
import { ApiError } from "../api/client";
import svelteSrc from "./WallOverlay.svelte?raw";

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

  const grid = makeGrid((over.grid as Record<string, unknown>) ?? {});
  const result = render(WallOverlay, {
    id: (over.id as string) ?? "a",
    grid,
    perPage: (over.perPage as number) ?? 3,
    api: (over.api as Api) ?? makeApi(),
    toasts: (over.toasts as ReturnType<typeof makeToasts>) ?? makeToasts(),
    onstep,
    onclose,
  });
  return { ...result, onstep, onclose, grid };
}

describe("WallOverlay", () => {
  it("renders role dialog named 'Image viewer' with a Close button that has focus", () => {
    const { getByRole } = mount();
    const dialog = getByRole("dialog", { name: "Image viewer" });
    expect(dialog).toBeTruthy();
    const closeBtn = getByRole("button", { name: "Close" });
    expect(document.activeElement).toBe(closeBtn);
  });

  it("page label: plain text '1 / 3', no select or textbox; range text '1-3 of 7' visible; no First/Previous/Next/Last page buttons", () => {
    const { getByRole, getByText, queryByRole } = mount();
    expect(getByText("1 / 3")).toBeTruthy();
    expect(queryByRole("combobox")).toBeNull();
    expect(queryByRole("textbox")).toBeNull();
    expect((getByRole("dialog") as HTMLElement).textContent).toContain("1-3 of 7");
    expect(queryByRole("button", { name: "First page" })).toBeNull();
    expect(queryByRole("button", { name: "Previous page" })).toBeNull();
    expect(queryByRole("button", { name: "Next page" })).toBeNull();
    expect(queryByRole("button", { name: "Last page" })).toBeNull();
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

  it("Previous image is enabled mid-page and steps back on click and ArrowLeft", async () => {
    const onstep = vi.fn();
    const { getByRole } = mount({ id: "b", onstep });
    const prev = getByRole("button", { name: "Previous image" }) as HTMLButtonElement;
    expect(prev.disabled).toBe(false);
    await fireEvent.click(prev);
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("a"));
    onstep.mockClear();
    await fireEvent.keyDown(getByRole("dialog"), { key: "ArrowLeft" });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("a"));
  });

  it("Previous image is enabled on the first item of page 2 and crosses back", async () => {
    const onstep = vi.fn();
    const { getByRole, grid } = mount({ id: "a", onstep, grid: { page: 2 } });
    const prev = getByRole("button", { name: "Previous image" }) as HTMLButtonElement;
    expect(prev.disabled).toBe(false);
    await fireEvent.click(prev);
    await waitFor(() => expect(grid.goTo).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onstep).toHaveBeenCalled());
  });

  it("Previous image is present but disabled on the first item of page 1", () => {
    const { getByRole } = mount({ id: "a" });
    const prev = getByRole("button", { name: "Previous image" }) as HTMLButtonElement;
    expect(prev.disabled).toBe(true);
  });

  it("the .nav rule has a z-index so Previous is not covered by the stage", () => {
    expect(svelteSrc).toMatch(/\.nav \{[^}]*z-index: 1;/);
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

  it("Escape calls onclose; ctrl+ArrowRight does not step", async () => {
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

describe("WallOverlay delete", () => {
  function delApi() {
    return makeApi({
      deleteItem: vi.fn(async () => ({ token: "t" })),
      restore: vi.fn(async () => ({})),
    });
  }

  function removingGrid(items: LibraryItem[]) {
    const removeById = vi.fn((k: string) => {
      const index = items.findIndex((it) => "image:" + it.id === k);
      if (index === -1) return null;
      const item = items[index];
      items.splice(index, 1);
      return { item, index };
    });
    return { items, removeById };
  }

  it("Delete key on 'b' calls deleteItem('images','b'), pushes an undo toast, steps to 'c'", async () => {
    const onstep = vi.fn();
    const toasts = makeToasts();
    const api = delApi();
    const items = makeItems();
    const gridOver = { ...removingGrid(items) };
    const { container, getByRole } = mount({ id: "b", api, toasts, onstep, grid: gridOver });
    const dialog = container.querySelector(".layer")!;
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    await fireEvent.keyDown(dialog, { key: "Delete" });
    await waitFor(() => expect(api.deleteItem).toHaveBeenCalledWith("images", "b"));
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("c"));
    expect(toasts.push).toHaveBeenCalledWith(expect.objectContaining({ kind: "undo" }));
  });

  it("Delete on last item 'c' with hasNext false, pages 1, page 1 steps to previous 'b'", async () => {
    const onstep = vi.fn();
    const toasts = makeToasts();
    const api = delApi();
    const items = makeItems();
    const gridOver = { ...removingGrid(items), hasNext: false, pages: 1, page: 1 };
    const { container, getByRole } = mount({ id: "c", api, toasts, onstep, grid: gridOver });
    const dialog = container.querySelector(".layer")!;
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    await fireEvent.keyDown(dialog, { key: "Delete" });
    await waitFor(() => expect(api.deleteItem).toHaveBeenCalledWith("images", "c"));
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
  });

  it("Delete on the only item closes", async () => {
    const onstep = vi.fn();
    const onclose = vi.fn();
    const toasts = makeToasts();
    const api = delApi();
    const items: LibraryItem[] = [
      { kind: "image", id: "a", title: "A", thumb_url: "/t/a", favorite: false, added_at: "2026-01-01" },
    ];
    const gridOver = { ...removingGrid(items), hasNext: false, pages: 1, page: 1 };
    const { container, getByRole } = mount({ id: "a", api, toasts, onstep, onclose, grid: gridOver });
    const dialog = container.querySelector(".layer")!;
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    await fireEvent.keyDown(dialog, { key: "Delete" });
    await waitFor(() => expect(api.deleteItem).toHaveBeenCalledWith("images", "a"));
    expect(onclose).toHaveBeenCalled();
    expect(onstep).not.toHaveBeenCalled();
  });

  it("two Delete presses make one deleteItem call", async () => {
    let resolveFn!: () => void;
    const promise = new Promise<{ token: string }>((res) => { resolveFn = () => res({ token: "t" }); });
    const deleteItem = vi.fn(() => promise);
    const api = makeApi({ deleteItem, restore: vi.fn(async () => ({})) });
    const onstep = vi.fn();
    const { container, getByRole } = mount({ id: "b", api, onstep });
    const dialog = container.querySelector(".layer")!;
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    fireEvent.keyDown(dialog, { key: "Delete" });
    fireEvent.keyDown(dialog, { key: "Delete" });
    expect(deleteItem).toHaveBeenCalledTimes(1);
    resolveFn();
    await promise;
    expect(deleteItem).toHaveBeenCalledTimes(1);
  });

  it("failed delete keeps the picture", async () => {
    const deleteItem = vi.fn(async () => { throw new Error("fail"); });
    const api = makeApi({ deleteItem, restore: vi.fn(async () => ({})) });
    const toasts = makeToasts();
    const onstep = vi.fn();
    const onclose = vi.fn();
    const { container, getByRole } = mount({ id: "b", api, toasts, onstep, onclose });
    const dialog = container.querySelector(".layer")!;
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    await fireEvent.keyDown(dialog, { key: "Delete" });
    await waitFor(() => expect(deleteItem).toHaveBeenCalledWith("images", "b"));
    expect(onstep).not.toHaveBeenCalled();
    expect(onclose).not.toHaveBeenCalled();
    expect(toasts.push).toHaveBeenCalledWith(expect.objectContaining({ kind: "error" }));
  });

  it("Delete button 'Delete' has class act and click deletes", async () => {
    const api = delApi();
    const { getByRole } = mount({ id: "b", api });
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    const btn = getByRole("button", { name: "Delete" });
    expect(btn.className).toContain("act");
    fireEvent.click(btn);
    await waitFor(() => expect(api.deleteItem).toHaveBeenCalledWith("images", "b"));
  });
});

describe("WallOverlay swipe", () => {
  function firePointer(
    el: HTMLElement,
    type: "pointerdown" | "pointerup" | "pointercancel",
    init: { pointerType: string; pointerId: number; clientX: number; clientY: number },
  ) {
    const event = new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      clientX: init.clientX,
      clientY: init.clientY,
    });
    Object.defineProperty(event, "pointerType", { value: init.pointerType });
    Object.defineProperty(event, "pointerId", { value: init.pointerId });
    return fireEvent(el, event);
  }

  async function getStageWrap(container: HTMLElement) {
    await waitFor(() => {
      expect(container.querySelector(".stage-wrap")?.getAttribute("aria-busy")).toBe("false");
    });
    return container.querySelector(".stage-wrap") as HTMLElement;
  }

  it("touch swipe left of 100px with dy 10 steps to next", async () => {
    const onstep = vi.fn();
    const { container } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    await firePointer(stageWrap, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "touch", pointerId: 1, clientX: 0, clientY: 60 });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
  });

  it("touch swipe right on id b steps to previous", async () => {
    const onstep = vi.fn();
    const { container } = mount({ id: "b", onstep });
    const stageWrap = await getStageWrap(container);
    await firePointer(stageWrap, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 0, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 60 });
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("a"));
  });

  it("a 40px touch swipe does not step", async () => {
    const onstep = vi.fn();
    const { container } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    await firePointer(stageWrap, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "touch", pointerId: 1, clientX: 60, clientY: 60 });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
  });

  it("a touch swipe with too much vertical motion does not step", async () => {
    const onstep = vi.fn();
    const { container } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    await firePointer(stageWrap, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "touch", pointerId: 1, clientX: 0, clientY: 150 });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
  });

  it("mouse pointer events do not step", async () => {
    const onstep = vi.fn();
    const { container } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    await firePointer(stageWrap, "pointerdown", { pointerType: "mouse", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "mouse", pointerId: 1, clientX: 0, clientY: 60 });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
  });

  it("pointercancel after a 100px touch move does not step", async () => {
    const onstep = vi.fn();
    const { container } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    await firePointer(stageWrap, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointercancel", { pointerType: "touch", pointerId: 1, clientX: 0, clientY: 50 });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
  });

  it("a touch swipe starting on the image button does not step", async () => {
    const onstep = vi.fn();
    const { container } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    const imgbtn = await waitFor(() => {
      const el = container.querySelector("button.imgbtn");
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    await firePointer(imgbtn, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "touch", pointerId: 1, clientX: 0, clientY: 60 });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
  });

  it("touch swipe is ignored while zoomed", async () => {
    const onstep = vi.fn();
    const { container, getByRole } = mount({ onstep });
    const stageWrap = await getStageWrap(container);
    const zoomBtn = getByRole("button", { name: "Zoom" });
    await fireEvent.click(zoomBtn);
    expect(zoomBtn.getAttribute("aria-pressed")).toBe("true");
    await firePointer(stageWrap, "pointerdown", { pointerType: "touch", pointerId: 1, clientX: 100, clientY: 50 });
    await firePointer(stageWrap, "pointerup", { pointerType: "touch", pointerId: 1, clientX: 0, clientY: 60 });
    await waitFor(() => {});
    expect(onstep).not.toHaveBeenCalled();
  });

  it("backdrop clicks on layer/mid close, but image click does not", async () => {
    const onclose = vi.fn();
    const { container } = mount({ onclose });
    const layer = container.querySelector(".layer") as HTMLElement;
    const mid = container.querySelector(".mid") as HTMLElement;
    const stageWrap = await getStageWrap(container);
    const img = await waitFor(() => {
      const el = stageWrap.querySelector("img");
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });

    fireEvent.click(img);
    expect(onclose).not.toHaveBeenCalled();

    fireEvent.click(mid);
    expect(onclose).toHaveBeenCalledTimes(1);

    fireEvent.click(layer);
    expect(onclose).toHaveBeenCalledTimes(2);
  });
});

describe("phone layout and motion (T-67)", () => {
  it("phone media query uses 719.98px breakpoint with grid-template-areas and 8px nav offsets", () => {
    expect(svelteSrc).toContain("max-width: 719.98px");
    expect(svelteSrc).toContain("grid-template-areas");
    expect(svelteSrc).toContain("left: 8px");
    expect(svelteSrc).toContain("right: 8px");
  });

  it("overlay-fade at 150ms; no prefers-reduced-motion or !important in component source", () => {
    expect(svelteSrc).toContain("overlay-fade");
    expect(svelteSrc).toContain("150ms");
    expect(svelteSrc).not.toContain("prefers-reduced-motion");
    expect(svelteSrc).not.toContain("!important");
  });

  it("bottom bar child order, no pager/Next page, close and page label present", async () => {
    const { container, getByRole, queryByRole } = mount();

    const bottom = container.querySelector(".bottom")!;
    const children = Array.from(bottom.children);
    expect(children[0].className).toContain("bar-left");
    expect(children[1].className).toContain("bar-name");
    expect(children[2].className).toContain("bar-right");

    expect(container.querySelector(".pager")).toBeNull();
    expect(queryByRole("button", { name: "Next page" })).toBeNull();

    expect(getByRole("button", { name: "Close" })).toBeTruthy();
    expect(container.querySelector(".page-text")).not.toBeNull();
  });

  it("source declares min-width: 44px and min-height: 44px", () => {
    expect(svelteSrc).toContain("min-width: 44px");
    expect(svelteSrc).toContain("min-height: 44px");
  });
});

describe("loading, errors and gone (T-67)", () => {
  function neverResolvingApi(): Api {
    return { ...makeApi({ getItem: vi.fn(() => new Promise(() => {})) }) } as unknown as Api;
  }

  it("a) loading: spinner, aria-busy true, img present, Delete disabled, Details aria-disabled, Next enabled", async () => {
    const { container, getByRole } = mount({ api: neverResolvingApi() });
    const stageWrap = container.querySelector(".stage-wrap")!;

    expect(stageWrap.getAttribute("aria-busy")).toBe("true");
    expect(stageWrap.querySelector(".spinner")).toBeTruthy();
    expect(stageWrap.querySelector("img")?.getAttribute("src")).toBe("/t/a");
    expect((getByRole("button", { name: "Delete" }) as HTMLButtonElement).disabled).toBe(true);
    expect(getByRole("link", { name: "Details" }).getAttribute("aria-disabled")).toBe("true");
    expect((getByRole("button", { name: "Next image" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("b) not in grid: no img, spinner visible", async () => {
    const { container } = mount({ id: "zzz", api: neverResolvingApi() });
    const stageWrap = container.querySelector(".stage-wrap")!;
    expect(stageWrap.querySelector("img")).toBeNull();
    expect(stageWrap.querySelector(".spinner")).toBeTruthy();
  });

  it("c) detail error: alert with Retry; after Retry getItem called twice, alert gone, img appears", async () => {
    let call = 0;
    const getItem = vi.fn(async (_k: string, id: string) => {
      call++;
      if (call === 1) throw new Error("boom");
      return {
        kind: "image", id, title: id.toUpperCase(), thumb_url: "/t/" + id,
        full_url: "/f/" + id, favorite: false, added_at: "2026-01-01",
        file_name: id + ".jpg", tags: [], rating: 3,
      };
    });
    const { container, getByRole, queryByRole } = mount({ api: { ...makeApi({ getItem }) } as unknown as Api });

    const alert = await waitFor(() =>
      getByRole("alert"),
    );
    expect(alert.textContent).toContain("Could not load this image");

    const retryBtn = getByRole("button", { name: "Retry" });
    await fireEvent.click(retryBtn);

    await waitFor(() => expect(getItem).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(queryByRole("alert")).toBeNull());
    expect(container.querySelector(".stage-wrap img")).toBeTruthy();
  });

  it("d) image error: alert appears; Retry clears alert and img src contains r=1", async () => {
    const { container, getByRole, queryByRole } = mount();

    const img = await waitFor(() => {
      const el = container.querySelector(".stage-wrap img");
      expect(el).toBeTruthy();
      return el as HTMLImageElement;
    });

    await waitFor(() => expect(container.querySelector(".stage-wrap")?.getAttribute("aria-busy")).toBe("false"));

    await fireEvent.error(img);
    const alert = await waitFor(() =>
      getByRole("alert"),
    );
    expect(alert.textContent).toContain("Could not load this image");

    const retryBtn = getByRole("button", { name: "Retry" });
    await fireEvent.click(retryBtn);

    await waitFor(() => expect(queryByRole("alert")).toBeNull());
    const newImg = container.querySelector(".stage-wrap img") as HTMLImageElement;
    expect(newImg.getAttribute("src")).toContain("r=1");
  });

  it("e) 404: removeById called, toast pushed, onstep to 'b'", async () => {
    const onstep = vi.fn();
    const toasts = makeToasts();
    const grid = makeGrid();
    const getItem = vi.fn(async () => { throw new ApiError(404, "not_found", "gone"); });
    mount({ id: "a", api: { ...makeApi({ getItem }) } as unknown as Api, toasts, onstep, grid });

    await waitFor(() => expect(grid.removeById).toHaveBeenCalledWith("image:a"));
    expect(toasts.push).toHaveBeenCalledWith(expect.objectContaining({ message: "This image is gone" }));
    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
  });

  it("f) 404 on last item 'c': onstep called with 'b'", async () => {
    const onstep = vi.fn();
    const grid = makeGrid();
    const getItem = vi.fn(async () => { throw new ApiError(404, "not_found", "gone"); });
    mount({ id: "c", api: { ...makeApi({ getItem }) } as unknown as Api, onstep, grid });

    await waitFor(() => expect(onstep).toHaveBeenCalledWith("b"));
  });

  it("g) Details link aria-disabled false and Delete enabled once ready", async () => {
    const { getByRole } = mount();

    await waitFor(() => {
      const radio = getByRole("radio", { name: "Rating 3 of 5" });
      expect(radio.getAttribute("aria-checked")).toBe("true");
    });

    const link = getByRole("link", { name: "Details" });
    expect(link.getAttribute("aria-disabled")).toBe("false");
    expect((getByRole("button", { name: "Delete" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("WallOverlay fullscreen", () => {
  function setFs(enabled: boolean, req: () => Promise<void>) {
    Object.defineProperty(document, "fullscreenEnabled", { configurable: true, value: enabled });
    HTMLElement.prototype.requestFullscreen = req as never;
  }
  function setFsEl(el: Element | null) {
    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: el });
  }

  afterEach(() => {
    delete (document as never as Record<string, unknown>).fullscreenEnabled;
    delete (document as never as Record<string, unknown>).fullscreenElement;
    delete (HTMLElement.prototype as never as Record<string, unknown>).requestFullscreen;
  });

  it("fullscreen button sits between Zoom and Details", () => {
    setFs(true, vi.fn(async () => {}));
    const { getByRole } = mount();
    const zoom = getByRole("button", { name: "Zoom" });
    const fs = getByRole("button", { name: "Fullscreen" });
    const details = getByRole("link", { name: "Details" });
    expect(zoom.compareDocumentPosition(fs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(fs.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("click requests fullscreen on the overlay element", async () => {
    const req = vi.fn(async () => {});
    setFs(true, req);
    const { getByRole } = mount();
    const dialog = getByRole("dialog");
    await fireEvent.click(getByRole("button", { name: "Fullscreen" }));
    expect(req.mock.contexts[0]).toBe(dialog);
  });

  it("icon label flips on fullscreenchange", async () => {
    setFs(true, vi.fn(async () => {}));
    const { getByRole } = mount();
    const dialog = getByRole("dialog");

    setFsEl(dialog);
    document.dispatchEvent(new Event("fullscreenchange"));
    await waitFor(() => {
      const btn = getByRole("button", { name: "Exit fullscreen" });
      expect(btn.getAttribute("aria-pressed")).toBe("true");
    });

    setFsEl(null);
    document.dispatchEvent(new Event("fullscreenchange"));
    await waitFor(() => {
      expect(getByRole("button", { name: "Fullscreen" })).toBeTruthy();
    });
  });

  it("closing while fullscreen exits fullscreen", async () => {
    // Close button
    document.exitFullscreen = vi.fn(async () => {}) as never;
    setFs(true, vi.fn(async () => {}));
    const onclose1 = vi.fn();
    const m1 = mount({ onclose: onclose1 });
    const dialog1 = m1.getByRole("dialog");
    setFsEl(dialog1);
    await fireEvent.click(m1.getByRole("button", { name: "Close" }));
    expect(document.exitFullscreen).toHaveBeenCalled();
    expect(onclose1).toHaveBeenCalled();
    m1.unmount();

    // Escape key
    document.exitFullscreen = vi.fn(async () => {}) as never;
    setFs(true, vi.fn(async () => {}));
    const onclose2 = vi.fn();
    const m2 = mount({ onclose: onclose2 });
    const dialog2 = m2.container.querySelector(".layer")!;
    setFsEl(dialog2);
    await fireEvent.keyDown(dialog2, { key: "Escape" });
    expect(document.exitFullscreen).toHaveBeenCalled();
    expect(onclose2).toHaveBeenCalled();
  });

  it("unmount while fullscreen exits fullscreen", async () => {
    document.exitFullscreen = vi.fn(async () => {}) as never;
    setFs(true, vi.fn(async () => {}));
    const { container, unmount } = mount();
    const dialog = container.querySelector(".layer")!;
    setFsEl(dialog);
    unmount();
    expect(document.exitFullscreen).toHaveBeenCalled();
  });

  it("delete while fullscreen exits fullscreen before the delete request", async () => {
    const order: string[] = [];
    document.exitFullscreen = vi.fn(async () => { order.push("exit"); }) as never;
    setFs(true, vi.fn(async () => {}));
    const api = makeApi({
      deleteItem: vi.fn(async () => { order.push("delete"); return { token: "t" }; }),
      restore: vi.fn(async () => ({})),
    });
    const { container, getByRole } = mount({ id: "b", api });
    const dialog = container.querySelector(".layer")!;
    await waitFor(() => expect(getByRole("radio", { name: "Rating 3 of 5" }).getAttribute("aria-checked")).toBe("true"));
    setFsEl(dialog);
    await fireEvent.keyDown(dialog, { key: "Delete" });
    await waitFor(() => expect(api.deleteItem).toHaveBeenCalled());
    expect(order[0]).toBe("exit");
    expect(order).toContain("delete");
  });

  it("button absent when fullscreenEnabled is false", () => {
    setFs(false, vi.fn(async () => {}));
    const { queryByRole } = mount();
    expect(queryByRole("button", { name: /fullscreen/i })).toBeNull();
  });

  it("rejected requestFullscreen does not throw", async () => {
    const req = vi.fn(() => Promise.reject(new Error("no")));
    setFs(true, req as never);
    const { getByRole } = mount();
    const btn = getByRole("button", { name: "Fullscreen" });
    await fireEvent.click(btn);
    await Promise.resolve();
    expect(req).toHaveBeenCalled();
  });
});
