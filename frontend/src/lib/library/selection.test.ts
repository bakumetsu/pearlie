// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import Tile from "../components/Tile.svelte";
import SelectBar from "../components/SelectBar.svelte";
import { createSelection, selection } from "./selection.svelte";
import { toasts } from "../stores/toasts.svelte";
import { API_CONTEXT_KEY } from "../api/client";
import type { Api, LibraryItem } from "../api/client";

const item = { kind: "image", id: "7", title: "Cat", thumb_url: "/t.jpg" } as unknown as LibraryItem;

describe("library selection", () => {
  afterEach(() => {
    cleanup();
    selection.clear();
    toasts.dismiss();
  });

  it("the pick button selects a tile and enters select mode", async () => {
    render(Tile, { item, href: "/x", selectable: true });
    const pick = screen.getByRole("button", { name: "Select Cat" });
    expect(pick.getAttribute("aria-pressed")).toBe("false");
    await fireEvent.click(pick);
    expect(selection.active).toBe(true);
    expect(selection.count).toBe(1);
    expect(pick.getAttribute("aria-pressed")).toBe("true");
  });

  it("a Tile without selectable has no Select button", () => {
    render(Tile, { item, href: "/x" });
    expect(screen.queryByRole("button", { name: "Select Cat" })).toBeNull();
  });

  it("in select mode a tile click toggles instead of navigating", async () => {
    const onnavigate = vi.fn();
    const { container } = render(Tile, { item, href: "/x", onnavigate, selectable: true });
    selection.toggle(item);
    await fireEvent.click(container.querySelector("a.tile")!);
    expect(onnavigate).not.toHaveBeenCalled();
    expect(selection.count).toBe(0);
  });

  it("Escape leaves select mode", async () => {
    render(SelectBar, { props: { onchanged: () => {} }, context: new Map([[API_CONTEXT_KEY, {} as Api]]) });
    selection.toggle(item);
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(selection.active).toBe(false);
  });

  it("trashPicked posts the batch and shows an Undo toast that restores the group", async () => {
    const api = {
      trashItems: vi.fn().mockResolvedValue({ group: "g1", results: [{}], failed: [] }),
      restoreGroup: vi.fn().mockResolvedValue({ restored: [{}], failed: [] }),
    } as unknown as Api;
    const sel = createSelection();
    sel.toggle(item);
    const changed = vi.fn();
    await sel.trashPicked(api, changed);
    expect(api.trashItems).toHaveBeenCalledWith([{ kind: "image", id: "7" }]);
    expect(sel.active).toBe(false);
    expect(changed).toHaveBeenCalled();
    expect(toasts.current?.kind).toBe("undo");
    expect(toasts.current?.durationMs).toBe(8000);
    toasts.runAction();
    await vi.waitFor(() => expect(api.restoreGroup).toHaveBeenCalledWith("g1"));
  });

  it("a partial failure says how many failed", async () => {
    const api = {
      trashItems: vi.fn().mockResolvedValue({ group: "g", results: [{}], failed: [{ kind: "image", id: "9", code: "x" }] }),
    } as unknown as Api;
    const sel = createSelection();
    sel.toggle(item);
    await sel.trashPicked(api, () => {});
    expect(toasts.current?.message).toContain("1 failed");
  });

  it("all failed with trash_unavailable shows the folder error and no Undo", async () => {
    const api = {
      trashItems: vi.fn().mockResolvedValue({
        group: "g", results: [], failed: [{ kind: "image", id: "7", code: "trash_unavailable" }],
      }),
    } as unknown as Api;
    const sel = createSelection();
    sel.toggle(item);
    await sel.trashPicked(api, () => {});
    expect(toasts.current?.kind).toBe("error");
    expect(toasts.current?.message).toContain("Trash folder not available");
  });
});
