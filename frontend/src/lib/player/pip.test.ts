import { describe, it, expect, vi } from "vitest";
import {
  pipSupported,
  isPipActive,
  enterPip,
  exitPip,
  setMediaSession,
  type PipVideo,
  type SessionHandlers,
} from "./pip";

function fakeVideo(overrides: Record<string, unknown> = {}): PipVideo {
  return {
    requestPictureInPicture: undefined,
    webkitSetPresentationMode: undefined,
    webkitPresentationMode: undefined,
    webkitSupportsPresentationMode: undefined,
    ...overrides,
  } as unknown as PipVideo;
}

function fakeDoc(overrides: Record<string, unknown> = {}): Document {
  return {
    pictureInPictureEnabled: false,
    pictureInPictureElement: null,
    exitPictureInPicture: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Document;
}

function fakeNav(overrides: Record<string, unknown> = {}): Navigator {
  return { ...overrides } as unknown as Navigator;
}

describe("pipSupported", () => {
  it("returns false when video is null", () => {
    const doc = fakeDoc();
    expect(pipSupported(doc, null)).toBe(false);
  });

  it("returns true for standard support", () => {
    const doc = fakeDoc({ pictureInPictureEnabled: true });
    const v = fakeVideo({ requestPictureInPicture: vi.fn() });
    expect(pipSupported(doc, v)).toBe(true);
  });

  it("returns false when pictureInPictureEnabled is false and no webkit", () => {
    const doc = fakeDoc({ pictureInPictureEnabled: false });
    const v = fakeVideo();
    expect(pipSupported(doc, v)).toBe(false);
  });

  it("returns true for webkit-only support", () => {
    const doc = fakeDoc({ pictureInPictureEnabled: false });
    const v = fakeVideo({ webkitSetPresentationMode: vi.fn() });
    expect(pipSupported(doc, v)).toBe(true);
  });

  it("returns false when webkit reports mode unsupported", () => {
    const doc = fakeDoc({ pictureInPictureEnabled: false });
    const v = fakeVideo({
      webkitSetPresentationMode: vi.fn(),
      webkitSupportsPresentationMode: vi.fn().mockReturnValue(false),
    });
    expect(pipSupported(doc, v)).toBe(false);
  });
});

describe("isPipActive", () => {
  it("returns true when pictureInPictureElement matches the video", () => {
    const v = fakeVideo();
    const doc = fakeDoc({ pictureInPictureElement: v });
    expect(isPipActive(doc, v)).toBe(true);
  });

  it("returns true when webkitPresentationMode is picture-in-picture", () => {
    const v = fakeVideo({ webkitPresentationMode: "picture-in-picture" });
    const doc = fakeDoc();
    expect(isPipActive(doc, v)).toBe(true);
  });

  it("returns false when neither condition holds", () => {
    const v = fakeVideo();
    const doc = fakeDoc();
    expect(isPipActive(doc, v)).toBe(false);
  });
});

describe("enterPip", () => {
  it("uses the standard API and resolves true", async () => {
    const doc = fakeDoc();
    const reqPip = vi.fn().mockResolvedValue(undefined);
    const v = fakeVideo({ requestPictureInPicture: reqPip });
    await expect(enterPip(doc, v)).resolves.toBe(true);
    expect(reqPip).toHaveBeenCalledTimes(1);
  });

  it("falls back to webkit when standard API is absent", async () => {
    const doc = fakeDoc();
    const webkitSet = vi.fn();
    const v = fakeVideo({ webkitSetPresentationMode: webkitSet });
    await expect(enterPip(doc, v)).resolves.toBe(true);
    expect(webkitSet).toHaveBeenCalledWith("picture-in-picture");
  });

  it("resolves false when no API is available", async () => {
    const doc = fakeDoc();
    const v = fakeVideo();
    await expect(enterPip(doc, v)).resolves.toBe(false);
  });

  it("resolves false when the standard call rejects", async () => {
    const doc = fakeDoc();
    const reqPip = vi.fn().mockRejectedValue(new Error("boom"));
    const v = fakeVideo({ requestPictureInPicture: reqPip });
    await expect(enterPip(doc, v)).resolves.toBe(false);
  });
});

describe("exitPip", () => {
  it("calls exitPictureInPicture when the standard element is set", async () => {
    const v = fakeVideo();
    const exitFn = vi.fn().mockResolvedValue(undefined);
    const doc = fakeDoc({ pictureInPictureElement: v, exitPictureInPicture: exitFn });
    await exitPip(doc, v);
    expect(exitFn).toHaveBeenCalledTimes(1);
  });

  it("falls back to webkit inline mode", async () => {
    const webkitSet = vi.fn();
    const v = fakeVideo({
      webkitPresentationMode: "picture-in-picture",
      webkitSetPresentationMode: webkitSet,
    });
    const doc = fakeDoc({ pictureInPictureElement: null });
    await exitPip(doc, v);
    expect(webkitSet).toHaveBeenCalledWith("inline");
  });
});

describe("setMediaSession", () => {
  it("does nothing (no throw) when mediaSession is absent from nav", () => {
    const nav = fakeNav({});
    const h: SessionHandlers = { play: vi.fn(), pause: vi.fn() };
    expect(() => setMediaSession(nav, { title: "t", poster: "p" }, h)).not.toThrow();
  });

  it("clears metadata and all handlers when meta is null", () => {
    const setHandler = vi.fn();
    const mediaSession = { metadata: "old", setActionHandler: setHandler };
    const nav = { mediaSession } as unknown as Navigator;
    const h: SessionHandlers = { play: vi.fn(), pause: vi.fn() };
    setMediaSession(nav, null, h);
    expect(mediaSession.metadata).toBeNull();
    expect(setHandler).toHaveBeenCalledWith("play", null);
    expect(setHandler).toHaveBeenCalledWith("pause", null);
    expect(setHandler).toHaveBeenCalledWith("enterpictureinpicture", null);
  });

  it("registers play, pause, and enterpictureinpicture when enterPip handler is given", () => {
    const setHandler = vi.fn();
    const mediaSession = { metadata: null, setActionHandler: setHandler };
    const nav = { mediaSession } as unknown as Navigator;
    const h: SessionHandlers = { play: vi.fn(), pause: vi.fn(), enterPip: vi.fn() };
    vi.stubGlobal("MediaMetadata", class { constructor(public init: unknown) {} });
    setMediaSession(nav, { title: "Song", poster: "cover.png" }, h);
    expect(setHandler).toHaveBeenCalledWith("play", h.play);
    expect(setHandler).toHaveBeenCalledWith("pause", h.pause);
    expect(setHandler).toHaveBeenCalledWith("enterpictureinpicture", h.enterPip);
  });

  it("does not register enterpictureinpicture when enterPip handler is absent", () => {
    const setHandler = vi.fn();
    const mediaSession = { metadata: null, setActionHandler: setHandler };
    const nav = { mediaSession } as unknown as Navigator;
    const h: SessionHandlers = { play: vi.fn(), pause: vi.fn() };
    vi.stubGlobal("MediaMetadata", class { constructor(public init: unknown) {} });
    setMediaSession(nav, { title: "Song", poster: "cover.png" }, h);
    expect(setHandler).toHaveBeenCalledWith("play", h.play);
    expect(setHandler).toHaveBeenCalledWith("pause", h.pause);
    expect(setHandler).not.toHaveBeenCalledWith("enterpictureinpicture", expect.anything());
  });

  it("survives a throwing setActionHandler for enterpictureinpicture", () => {
    const setHandler = vi.fn().mockImplementation((action: string) => {
      if (action === "enterpictureinpicture") throw new Error("unsupported");
    });
    const mediaSession = { metadata: null, setActionHandler: setHandler };
    const nav = { mediaSession } as unknown as Navigator;
    const h: SessionHandlers = { play: vi.fn(), pause: vi.fn(), enterPip: vi.fn() };
    vi.stubGlobal("MediaMetadata", class { constructor(public init: unknown) {} });
    expect(() => setMediaSession(nav, { title: "Song", poster: "cover.png" }, h)).not.toThrow();
    expect(setHandler).toHaveBeenCalledWith("play", h.play);
    expect(setHandler).toHaveBeenCalledWith("pause", h.pause);
  });
});
