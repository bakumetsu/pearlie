const revealed = new Set<string>();

export function mediaSrc(el: Element): string {
  if (el instanceof HTMLImageElement) return el.src || el.currentSrc;
  if (el instanceof HTMLVideoElement) return el.poster || el.currentSrc || el.src;
  return "";
}

export function revealTarget(
  target: EventTarget | null,
  root: HTMLElement,
): Element | null {
  if (root.dataset.sfw !== "on") return null;
  if (!(target instanceof Element)) return null;

  let el: Element | null;
  if (target instanceof HTMLImageElement || target instanceof HTMLVideoElement) {
    el = target;
  } else {
    const tile = target.closest(".tile");
    el = tile ? tile.querySelector("img") : null;
  }

  return el !== null && !el.hasAttribute("data-sfw-shown") && mediaSrc(el) !== "" ? el : null;
}

export function reveal(el: Element): void {
  const src = mediaSrc(el);
  if (src === "") return;
  revealed.add(src);
  el.setAttribute("data-sfw-shown", "1");
}

export function resetReveals(root: HTMLElement): void {
  revealed.clear();
  root.querySelectorAll("[data-sfw-shown]").forEach((node) => {
    node.removeAttribute("data-sfw-shown");
  });
}

export function syncReveal(el: Element): void {
  const src = mediaSrc(el);
  if (el.hasAttribute("data-sfw-shown")) {
    if (!revealed.has(src)) el.removeAttribute("data-sfw-shown");
  } else if (revealed.has(src)) {
    el.setAttribute("data-sfw-shown", "1");
  }
}

export function installReveal(root: HTMLElement = document.documentElement): () => void {
  const onClick = (event: MouseEvent): void => {
    const el = revealTarget(event.target, root);
    if (el) {
      reveal(el);
      event.preventDefault();
      event.stopPropagation();
    }
  };

  const onMediaEvent = (event: Event): void => {
    const t = event.target;
    if (t instanceof HTMLImageElement || t instanceof HTMLVideoElement) {
      syncReveal(t);
    }
  };

  const observer = new MutationObserver((records) => {
    for (const r of records) {
      const t = r.target;
      if (t instanceof HTMLImageElement || t instanceof HTMLVideoElement) syncReveal(t);
    }
  });
  observer.observe(root, {
    subtree: true,
    attributes: true,
    attributeFilter: ["src", "srcset", "poster"],
  });
  document.addEventListener("click", onClick, true);
  document.addEventListener("load", onMediaEvent, true);
  document.addEventListener("loadstart", onMediaEvent, true);

  return (): void => {
    observer.disconnect();
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("load", onMediaEvent, true);
    document.removeEventListener("loadstart", onMediaEvent, true);
  };
}
