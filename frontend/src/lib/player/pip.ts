export type PipVideo = HTMLVideoElement & {
  webkitSetPresentationMode?: (mode: string) => void;
  webkitPresentationMode?: string;
  webkitSupportsPresentationMode?: (mode: string) => boolean;
};

export function pipSupported(doc: Document, v: PipVideo | null): boolean {
  if (v === null) return false;

  const standard =
    doc.pictureInPictureEnabled === true &&
    typeof v.requestPictureInPicture === "function";

  const webkit =
    typeof v.webkitSetPresentationMode === "function" &&
    (v.webkitSupportsPresentationMode
      ? v.webkitSupportsPresentationMode("picture-in-picture")
      : true);

  return standard || webkit;
}

export function isPipActive(doc: Document, v: PipVideo | null): boolean {
  if (v === null) return false;
  if (doc.pictureInPictureElement === v) return true;
  return v.webkitPresentationMode === "picture-in-picture";
}

export async function enterPip(doc: Document, v: PipVideo): Promise<boolean> {
  if (typeof v.requestPictureInPicture === "function") {
    try {
      await v.requestPictureInPicture();
      return true;
    } catch {
      return false;
    }
  }

  if (typeof v.webkitSetPresentationMode === "function") {
    try {
      v.webkitSetPresentationMode("picture-in-picture");
      return true;
    } catch {
      return false;
    }
  }

  return false;
}

export async function exitPip(doc: Document, v: PipVideo): Promise<void> {
  if (doc.pictureInPictureElement) {
    try {
      await doc.exitPictureInPicture();
    } catch {
      // swallow
    }
    return;
  }

  if (
    v.webkitPresentationMode === "picture-in-picture" &&
    typeof v.webkitSetPresentationMode === "function"
  ) {
    try {
      v.webkitSetPresentationMode("inline");
    } catch {
      // swallow
    }
  }
}

export type SessionHandlers = {
  play: () => void;
  pause: () => void;
  enterPip?: () => void;
  prev?: (() => void) | null;
  next?: (() => void) | null;
};

export function setMediaSession(
  nav: Navigator,
  meta: { title: string; poster: string } | null,
  h: SessionHandlers,
): void {
  if (!("mediaSession" in nav)) return;

  const ms = nav.mediaSession;
  const enterPipAction = "enterpictureinpicture" as unknown as MediaSessionAction;
  const setTrack = (action: MediaSessionAction, fn: (() => void) | null | undefined): void => {
    try { ms.setActionHandler(action, fn ?? null); } catch { /* unsupported */ }
  };

  if (meta === null) {
    ms.metadata = null;
    try { ms.setActionHandler("play", null); } catch { /* unsupported */ }
    try { ms.setActionHandler("pause", null); } catch { /* unsupported */ }
    try { ms.setActionHandler(enterPipAction, null); } catch { /* unsupported */ }
    setTrack("previoustrack", null);
    setTrack("nexttrack", null);
    return;
  }

  ms.metadata = new MediaMetadata({
    title: meta.title,
    artwork: [{ src: meta.poster }],
  });

  try { ms.setActionHandler("play", h.play); } catch { /* unsupported */ }
  try { ms.setActionHandler("pause", h.pause); } catch { /* unsupported */ }

  setTrack("previoustrack", h.prev);
  setTrack("nexttrack", h.next);

  if (h.enterPip) {
    try { ms.setActionHandler(enterPipAction, h.enterPip); } catch { /* unsupported */ }
  }
}

/** Calls on(true/false) when the video enters or leaves PiP (standard and WebKit events). */
export function watchPip(v: PipVideo, on: (active: boolean) => void): () => void {
  const enter = () => on(true);
  const leave = () => on(false);
  const webkit = () => on(v.webkitPresentationMode === "picture-in-picture");
  v.addEventListener("enterpictureinpicture", enter);
  v.addEventListener("leavepictureinpicture", leave);
  v.addEventListener("webkitpresentationmodechanged", webkit);
  return () => {
    v.removeEventListener("enterpictureinpicture", enter);
    v.removeEventListener("leavepictureinpicture", leave);
    v.removeEventListener("webkitpresentationmodechanged", webkit);
  };
}
