import { describe, it, expect, vi } from "vitest";
import { createPlacement } from "./placement.svelte";
import type { Api, WebItem } from "../api/client";

const item = { source: "nhentai", post_id: "7", target: "komga" } as WebItem;
const sug = { kind: "oneshot", series: null, number: null, joins_existing: false, moves_first: false, reason: "new" };

function make(mode: string, getPlacement = vi.fn().mockResolvedValue(sug)) {
  const store = createPlacement({ api: () => ({ getPlacement }) as unknown as Api, mode: () => mode });
  return { store, getPlacement };
}

describe("placement store", () => {
  it("skips the sheet in auto mode and for other sources", async () => {
    const { store, getPlacement } = make("auto");
    expect(await store.ask(item)).toEqual({});
    const s2 = make("suggest");
    expect(await s2.store.ask({ source: "danbooru", post_id: "1", target: "stash" } as WebItem)).toEqual({});
    expect(getPlacement).not.toHaveBeenCalled();
  });

  it("sends the confirmed kind even when unchanged", async () => {
    const { store } = make("suggest");
    const p = store.ask(item);
    await vi.waitFor(() => expect(store.loading).toBe(false));
    expect(store.kind).toBe("oneshot");
    store.confirm();
    expect(await p).toEqual({ placement: { kind: "oneshot" } });
  });

  it("sends the override after one tap", async () => {
    const { store } = make("suggest");
    const p = store.ask(item);
    await vi.waitFor(() => expect(store.loading).toBe(false));
    store.toggle();
    store.confirm();
    expect(await p).toEqual({ placement: { kind: "series" } });
  });

  it("returns null when closed, and cannot confirm while loading", async () => {
    const { store } = make("suggest", vi.fn().mockReturnValue(new Promise(() => {})));
    const p = store.ask(item);
    store.confirm();
    expect(store.item).not.toBeNull();
    store.cancel();
    expect(await p).toBeNull();
  });
});
