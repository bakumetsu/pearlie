// One shared IntersectionObserver: tells a node when it enters or leaves the viewport.
type Cb = (visible: boolean) => void;

const callbacks = new WeakMap<Element, Cb>();
let observer: IntersectionObserver | null = null;

function shared(): IntersectionObserver | null {
  if (typeof IntersectionObserver === "undefined") return null;
  observer ??= new IntersectionObserver(
    (entries) => {
      for (const e of entries) callbacks.get(e.target)?.(e.isIntersecting);
    },
    { rootMargin: "100px" },
  );
  return observer;
}

export function inView(node: Element, cb: Cb) {
  callbacks.set(node, cb);
  shared()?.observe(node);
  return {
    update(next: Cb) {
      callbacks.set(node, next);
    },
    destroy() {
      shared()?.unobserve(node);
      callbacks.delete(node);
    },
  };
}
