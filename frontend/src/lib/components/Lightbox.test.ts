// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import Lightbox from "./Lightbox.svelte";
import { installReveal, REVEAL_DELAY_MS } from "../stores/sfw-reveal";

// jsdom lacks dialog.showModal / close
HTMLDialogElement.prototype.showModal = function () {};
HTMLDialogElement.prototype.close = function () {};

function ptrEvent(
  type: string,
  opts: { pointerType?: string; relatedTarget?: Element | null } = {},
): Event {
  const { pointerType = "mouse", relatedTarget = null } = opts;
  if (typeof PointerEvent !== "undefined") {
    return new PointerEvent(type, {
      bubbles: true,
      pointerType,
      ...(relatedTarget ? { relatedTarget } : {}),
    } as PointerEventInit);
  }
  const ev = new MouseEvent(type, {
    bubbles: true,
    ...(relatedTarget ? { relatedTarget } : {}),
  });
  Object.defineProperty(ev, "pointerType", { value: pointerType });
  return ev;
}

const cases = [
  { width: 600, height: 900, label: "portrait" },
  { width: 900, height: 600, label: "landscape" },
];

function renderItem(width: number, height: number) {
  const item = {
    source: "x",
    post_id: "1",
    preview_url: "http://mock/p.jpg",
    thumb_url: "http://mock/t.jpg",
    width,
    height,
    tags: [],
  } as never;
  return render(Lightbox, {
    props: { item, onsave: () => {}, onclose: () => {} },
  });
}

describe("Lightbox", () => {
  let dispose: (() => void) | undefined;

  afterEach(() => {
    dispose?.();
    dispose = undefined;
    cleanup();
    delete document.documentElement.dataset.sfw;
    vi.useRealTimers();
  });

  it("shows Save for a saveable item and hides it when saveable is false", () => {
    for (const [saveable, count] of [[true, 1], [false, 0]] as const) {
      const item = { source: "x", post_id: "1", preview_url: "http://mock/p.jpg", thumb_url: "http://mock/t.jpg", width: 10, height: 10, tags: [], saveable } as never;
      const r = render(Lightbox, { props: { item, onsave: () => {}, onclose: () => {} } });
      expect(document.querySelectorAll(".save-btn").length).toBe(count);
      r.unmount();
    }
  });

  it.each(cases)(
    "$label pointerover on .stage does NOT reveal img",
    ({ width, height }) => {
      document.documentElement.dataset.sfw = "on";
      vi.useFakeTimers();
      dispose = installReveal();

      renderItem(width, height);

      const stage = document.querySelector(".stage")!;
      stage.dispatchEvent(ptrEvent("pointerover", { pointerType: "mouse" }));

      vi.advanceTimersByTime(REVEAL_DELAY_MS + 10);

      const img = document.querySelector(".stage img")!;
      expect(img.hasAttribute("data-sfw-shown")).toBe(false);
    },
  );

  it.each(cases)(
    "$label pointerover on img reveals; pointerout to .stage re-blurs",
    ({ width, height }) => {
      document.documentElement.dataset.sfw = "on";
      vi.useFakeTimers();
      dispose = installReveal();

      renderItem(width, height);

      const img = document.querySelector(".stage img")!;
      const stage = document.querySelector(".stage")!;

      img.dispatchEvent(ptrEvent("pointerover", { pointerType: "mouse" }));
      vi.advanceTimersByTime(REVEAL_DELAY_MS + 10);
      expect(img.hasAttribute("data-sfw-shown")).toBe(true);

      img.dispatchEvent(
        ptrEvent("pointerout", { pointerType: "mouse", relatedTarget: stage }),
      );
      expect(img.hasAttribute("data-sfw-shown")).toBe(false);
    },
  );

  it.each(cases)(
    "$label img style has correct aspect-ratio",
    ({ width, height }) => {
      renderItem(width, height);

      const img = document.querySelector<HTMLImageElement>(".stage img")!;
      expect(img.style.aspectRatio).toBe(`${width} / ${height}`);
    },
  );

  it.each(cases)(
    "$label touch pointerover never reveals img",
    ({ width, height }) => {
      document.documentElement.dataset.sfw = "on";
      vi.useFakeTimers();
      dispose = installReveal();

      renderItem(width, height);

      const img = document.querySelector(".stage img")!;
      img.dispatchEvent(ptrEvent("pointerover", { pointerType: "touch" }));

      vi.advanceTimersByTime(REVEAL_DELAY_MS + 10);

      expect(img.hasAttribute("data-sfw-shown")).toBe(false);
    },
  );

  it("unknown size (0x0): no aspect-ratio style, empty stage still keeps blur", () => {
    document.documentElement.dataset.sfw = "on";
    vi.useFakeTimers();
    dispose = installReveal();

    renderItem(0, 0);

    const img = document.querySelector<HTMLImageElement>(".stage img")!;
    expect(img.getAttribute("style") ?? "").not.toContain("aspect-ratio");

    document.querySelector(".stage")!.dispatchEvent(ptrEvent("pointerover", { pointerType: "mouse" }));
    vi.advanceTimersByTime(REVEAL_DELAY_MS + 10);
    expect(img.hasAttribute("data-sfw-shown")).toBe(false);
  });
});
