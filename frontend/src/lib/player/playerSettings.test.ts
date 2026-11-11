import { describe, it, expect, vi } from "vitest";
import type { Api } from "../api/client";
import { createPlayerSettings } from "./playerSettings.svelte";
import { createPlayer } from "./player.svelte";

const push = vi.fn();
const toastsMock = { push } as never;

describe("createPlayerSettings", () => {
  it("default autoplay is false before load", () => {
    const s = createPlayerSettings(toastsMock);
    expect(s.autoplay).toBe(false);
  });

  it("load sets autoplay from getPlayerSettings", async () => {
    const api = {
      getPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: true })),
      putPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: true })),
    } as unknown as Api;
    const s = createPlayerSettings(toastsMock);
    s.load(api);
    await vi.waitFor(() => expect(s.autoplay).toBe(true));
  });

  it("failed load leaves autoplay false and pushes no toast", async () => {
    const api = {
      getPlayerSettings: vi.fn(() => Promise.reject(new Error("net"))),
      putPlayerSettings: vi.fn(),
    } as unknown as Api;
    const s = createPlayerSettings(toastsMock);
    s.load(api);
    await new Promise<void>(r => setTimeout(r, 0));
    expect(s.autoplay).toBe(false);
    expect(push).not.toHaveBeenCalled();
  });

  it("load twice calls the api only once", async () => {
    const api = {
      getPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: true })),
      putPlayerSettings: vi.fn(),
    } as unknown as Api;
    const s = createPlayerSettings(toastsMock);
    s.load(api);
    s.load(api);
    expect(api.getPlayerSettings).toHaveBeenCalledTimes(1);
  });

  it("setAutoplay(true) is optimistic and calls putPlayerSettings", async () => {
    const api = {
      getPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: false })),
      putPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: true })),
    } as unknown as Api;
    const s = createPlayerSettings(toastsMock);
    s.load(api);
    await vi.waitFor(() => expect(s.autoplay).toBe(false));
    const p = s.setAutoplay(true);
    expect(s.autoplay).toBe(true);
    expect(api.putPlayerSettings).toHaveBeenCalledWith({ autoplay: true });
    await p;
    expect(s.autoplay).toBe(true);
  });

  it("failed PUT reverts to previous value and pushes error toast", async () => {
    const api = {
      getPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: false })),
      putPlayerSettings: vi.fn(() => Promise.reject(new Error("net"))),
    } as unknown as Api;
    const s = createPlayerSettings(toastsMock);
    s.load(api);
    await vi.waitFor(() => expect(s.autoplay).toBe(false));
    const p = s.setAutoplay(true);
    expect(s.autoplay).toBe(true);
    await p;
    expect(s.autoplay).toBe(false);
    expect(push).toHaveBeenCalledWith({ kind: "error", message: "Could not save Autoplay" });
  });

  it("player created before load picks up autoplay after load", async () => {
    const api = {
      getPlayerSettings: vi.fn(() => Promise.resolve({ autoplay: true })),
      putPlayerSettings: vi.fn(),
    } as unknown as Api;
    const s = createPlayerSettings(toastsMock);
    const p = createPlayer(() => s.autoplay);
    const item = { id: "1", title: "A", streamUrl: "", posterUrl: "", href: "" };
    s.load(api);
    await vi.waitFor(() => expect(s.autoplay).toBe(true));
    p.open(item);
    expect(p.consumePlayOnLoad()).toBe(true);
  });
});
