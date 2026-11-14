// Client gate for web image requests (design D-21 section 3.2): one tab keeps at most
// 4 requests in flight, 2 for focus images and 2 for cover/prefetch images.
export type WebPrio = "focus" | "cover" | "prefetch";

export interface Gate {
  acquire(prio: WebPrio): { ready: Promise<() => void>; cancel: () => void };
}

type Job = { prio: WebPrio; grant: (release: () => void) => void; dead: boolean };

export function createGate(limits: { focus: number; other: number } = { focus: 2, other: 2 }): Gate {
  const lane = (p: WebPrio) => (p === "focus" ? "focus" : "other");
  const busy = { focus: 0, other: 0 };
  const queue: Record<"focus" | "other", Job[]> = { focus: [], other: [] };

  function start(job: Job, charged: "focus" | "other") {
    busy[charged]++;
    let done = false;
    job.grant(() => {
      if (done) return;
      done = true;
      busy[charged]--;
      pump();
    });
  }

  // Focus jobs may borrow an idle slot of the other lane; cover/prefetch never take focus slots.
  function pump() {
    for (const l of ["focus", "other"] as const) {
      queue[l] = queue[l].filter((j) => !j.dead);
    }
    while (queue.focus.length) {
      if (busy.focus < limits.focus) start(queue.focus.shift()!, "focus");
      else if (busy.other < limits.other) start(queue.focus.shift()!, "other");
      else break;
    }
    while (queue.other.length && busy.other < limits.other) start(queue.other.shift()!, "other");
  }

  return {
    acquire(prio) {
      const l = lane(prio);
      const job: Job = { prio, grant: () => {}, dead: false };
      const ready = new Promise<() => void>((resolve) => {
        job.grant = resolve;
      });
      const q = queue[l];
      // cover goes before prefetch; same prio keeps arrival order
      const at = prio === "cover" ? q.findIndex((j) => j.prio === "prefetch") : -1;
      if (at < 0) q.push(job);
      else q.splice(at, 0, job);
      pump();
      return {
        ready,
        cancel() {
          job.dead = true;
        },
      };
    },
  };
}

export const webGate = createGate();

// focus is the route default: no query, so the URL matches the reader thumbnail strip (browser cache hit)
export function withPrio(url: string, prio: WebPrio): string {
  if (prio === "focus") return url;
  return url + (url.includes("?") ? "&" : "?") + "prio=" + prio;
}

// Svelte action: sets the image src only when the gate grants a slot; frees it on load or error.
export function gatedSrc(node: HTMLImageElement, arg: { src: string; prio: WebPrio; gate?: Gate }) {
  let cancel: (() => void) | null = null;
  let release: (() => void) | null = null;

  function free() {
    release?.();
    release = null;
  }
  function start(a: { src: string; prio: WebPrio; gate?: Gate }) {
    cancel?.();
    free();
    node.removeAttribute("src");
    const h = (a.gate ?? webGate).acquire(a.prio);
    cancel = h.cancel;
    let live = true;
    const prev = cancel;
    cancel = () => {
      live = false;
      prev();
    };
    void h.ready.then((rel) => {
      if (!live) {
        rel();
        return;
      }
      release = rel;
      node.src = withPrio(a.src, a.prio);
    });
  }
  node.addEventListener("load", free);
  node.addEventListener("error", free);
  start(arg);
  return {
    update(a: { src: string; prio: WebPrio; gate?: Gate }) {
      start(a);
    },
    destroy() {
      cancel?.();
      free();
      node.removeEventListener("load", free);
      node.removeEventListener("error", free);
    },
  };
}
