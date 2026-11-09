let current: Element | null = null;
let mo: MutationObserver | null = null;

export function mediaSrc(el: Element): string {
  if (el instanceof HTMLImageElement) {
    return el.src || el.currentSrc;
  }
  if (el instanceof HTMLVideoElement) {
    return el.poster || el.currentSrc || el.src;
  }
  return "";
}

export function revealTarget(target: EventTarget | null, root: HTMLElement): Element | null {
  if (!(target instanceof Element)) return null;
  if (root.dataset.sfw !== "on") return null;
  const tile = target.closest(".tile");
  const el = tile
    ? tile.querySelector("img, video")
    : target instanceof HTMLImageElement || target instanceof HTMLVideoElement
      ? target
      : null;
  if (!el) return null;
  if (!mediaSrc(el)) return null;
  return el;
}

function hide(): void {
  if (mo) {
    mo.disconnect();
    mo = null;
  }
  if (current) {
    current.removeAttribute("data-sfw-shown");
    current = null;
  }
}

export function reveal(el: Element): void {
  hide();
  el.setAttribute("data-sfw-shown", "1");
  current = el;
  mo = new MutationObserver(() => hide());
  mo.observe(el, { attributes: true, attributeFilter: ["src", "srcset", "poster"] });
}

export function resetReveals(root: HTMLElement): void {
  root.querySelectorAll("[data-sfw-shown]").forEach((el) => el.removeAttribute("data-sfw-shown"));
  hide();
}

export function installReveal(root: HTMLElement = document.documentElement): () => void {
  let lastPointerType = "";

  const onPointerOver = (e: PointerEvent) => {
    if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
    const el = revealTarget(e.target, root);
    if (el) reveal(el);
  };

  const onPointerOut = (e: PointerEvent) => {
    if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
    if (!current) return;
    const el = revealTarget(e.target, root);
    if (!el || el !== current) return;
    const tile = el.closest(".tile");
    const related = e.relatedTarget;
    if (tile) {
      if (!(related instanceof Node) || !tile.contains(related)) hide();
    } else {
      if (!(related instanceof Node) || !el.contains(related)) hide();
    }
  };

  const onFocusIn = (e: FocusEvent) => {
    if (lastPointerType === "touch") return;
    const el = revealTarget(e.target, root);
    if (el) reveal(el);
  };

  const onFocusOut = (e: FocusEvent) => {
    if (!current) return;
    const el = revealTarget(e.target, root);
    if (!el || el !== current) return;
    const tile = el.closest(".tile");
    const related = e.relatedTarget;
    if (tile) {
      if (!(related instanceof Node) || !tile.contains(related)) hide();
    } else {
      if (!(related instanceof Node) || !el.contains(related)) hide();
    }
  };

  const onPointerDown = (e: PointerEvent) => {
    lastPointerType = e.pointerType;
    if (e.pointerType !== "touch") return;
    if (root.dataset.sfw !== "on") return;
    if (current) {
      const tile = current.closest(".tile");
      const t = e.target;
      if (tile) {
        if (!(t instanceof Node) || !tile.contains(t)) hide();
      } else {
        if (!(t instanceof Node) || !current.contains(t)) hide();
      }
    }
  };

  const onKeyDown = () => {
    lastPointerType = "key";
  };

  const onClick = (e: MouseEvent) => {
    if (lastPointerType !== "touch") return;
    if (root.dataset.sfw !== "on") return;
    const el = revealTarget(e.target, root);
    if (el) {
      if (el !== current) {
        reveal(el);
        e.preventDefault();
        e.stopPropagation();
      }
    } else {
      hide();
    }
  };

  const onScroll = () => {
    if (root.dataset.sfw !== "on") return;
    if (lastPointerType === "touch") hide();
  };

  const onPageHide = () => {
    if (root.dataset.sfw !== "on") return;
    hide();
  };

  const onVisibilityChange = () => {
    if (root.dataset.sfw !== "on") return;
    if (document.visibilityState === "hidden") hide();
  };

  const onHashChange = () => {
    if (root.dataset.sfw !== "on") return;
    hide();
  };

  const onPopState = () => {
    if (root.dataset.sfw !== "on") return;
    hide();
  };

  document.addEventListener("pointerover", onPointerOver, true);
  document.addEventListener("pointerout", onPointerOut, true);
  document.addEventListener("focusin", onFocusIn, true);
  document.addEventListener("focusout", onFocusOut, true);
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("click", onClick, true);
  window.addEventListener("scroll", onScroll, true);
  window.addEventListener("pagehide", onPageHide);
  document.addEventListener("visibilitychange", onVisibilityChange);
  window.addEventListener("hashchange", onHashChange);
  window.addEventListener("popstate", onPopState);

  return () => {
    document.removeEventListener("pointerover", onPointerOver, true);
    document.removeEventListener("pointerout", onPointerOut, true);
    document.removeEventListener("focusin", onFocusIn, true);
    document.removeEventListener("focusout", onFocusOut, true);
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("keydown", onKeyDown, true);
    document.removeEventListener("click", onClick, true);
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("pagehide", onPageHide);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    window.removeEventListener("hashchange", onHashChange);
    window.removeEventListener("popstate", onPopState);
    hide();
  };
}
