// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/svelte";
import PlacementSheet from "./PlacementSheet.svelte";
import { createPlacement } from "../stores/placement.svelte";
import type { Api, WebItem } from "../api/client";

const item = { source: "nhentai", post_id: "7", target: "komga" } as WebItem;
const sug = { kind: "series", series: "[Foo] My Sister", number: "2", joins_existing: true, moves_first: true, reason: "folder" };

afterEach(() => cleanup());

describe("PlacementSheet", () => {
  it("shows the suggestion, flips with one tap and saves the override", async () => {
    const store = createPlacement({
      api: () => ({ getPlacement: vi.fn().mockResolvedValue(sug) }) as unknown as Api,
      mode: () => "suggest",
    });
    render(PlacementSheet, { store });
    const answer = store.ask(item);
    await waitFor(() => expect(screen.getByTestId("placement-line").textContent).toContain("[Foo] My Sister · vol 2"));
    expect(screen.getByTestId("placement-toggle").textContent).toContain("Make oneshot");
    await fireEvent.click(screen.getByTestId("placement-toggle"));
    expect(screen.getByTestId("placement-line").textContent).toBe("Oneshot");
    await fireEvent.click(screen.getByTestId("placement-save"));
    expect(await answer).toEqual({ placement: { kind: "oneshot" } });
    expect(screen.queryByTestId("placement-sheet")).toBeNull();
  });

  it("disables Save while loading", async () => {
    const store = createPlacement({
      api: () => ({ getPlacement: () => new Promise(() => {}) }) as unknown as Api,
      mode: () => "suggest",
    });
    render(PlacementSheet, { store });
    void store.ask(item);
    const btn = (await screen.findByTestId("placement-save")) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("closes on Escape, cancels the save and returns focus to the opener", async () => {
    const store = createPlacement({
      api: () => ({ getPlacement: vi.fn().mockResolvedValue(sug) }) as unknown as Api,
      mode: () => "suggest",
    });
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    render(PlacementSheet, { store });
    const answer = store.ask(item);
    const sheet = await screen.findByTestId("placement-sheet");
    await waitFor(() => expect(document.activeElement).toBe(sheet));
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(await answer).toBeNull();
    expect(screen.queryByTestId("placement-sheet")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(opener));
    opener.remove();
  });
});
