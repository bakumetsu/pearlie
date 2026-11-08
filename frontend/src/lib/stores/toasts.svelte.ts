
export type ToastKind = "info" | "error" | "undo";
export type Toast = { id: number; kind: ToastKind; message: string; actionLabel?: string; href?: string; onAction?: () => void; durationMs: number };

const DURATIONS: Record<ToastKind, number> = { info: 4000, error: 6000, undo: 10000 };

export function createToasts(timers?: { set: typeof setTimeout; clear: typeof clearTimeout }) {
  const timer = timers ?? { set: setTimeout, clear: clearTimeout };
  let nextId = 1;
  let current: Toast | null = $state(null);
  const queue: Toast[] = $state([]);
  let timerHandle: ReturnType<typeof setTimeout> | null = null;
  let remainingMs: number | null = null;
  let startAt: number | null = null;

  function startTimer(ms: number) {
    remainingMs = ms;
    startAt = Date.now();
    timerHandle = timer.set(() => {
      timerHandle = null; remainingMs = null; startAt = null;
      current = null;
      showNext();
    }, ms);
  }

  function stopTimer() {
    if (timerHandle !== null) { timer.clear(timerHandle); timerHandle = null; }
  }

  function showNext() {
    const next = queue.shift();
    if (next !== undefined) { current = next; startTimer(next.durationMs); }
  }

  function dismiss(id?: number) {
    if (id !== undefined && current?.id !== id) {
      const idx = queue.findIndex((q) => q.id === id);
      if (idx !== -1) queue.splice(idx, 1);
      return;
    }
    stopTimer(); remainingMs = null; startAt = null;
    current = null;
    showNext();
  }

  return {
    get current(): Toast | null { return current; },
    get queued(): number { return queue.length; },

    push(t: { kind: ToastKind; message: string; actionLabel?: string; href?: string; onAction?: () => void }): number {
      const id = nextId++;
      const toast: Toast = { id, kind: t.kind, message: t.message, actionLabel: t.actionLabel, href: t.href, onAction: t.onAction, durationMs: DURATIONS[t.kind] };
      if (current === null) { current = toast; startTimer(toast.durationMs); }
      else { queue.push(toast); }
      return id;
    },

    dismiss,

    pause() {
      if (startAt === null) return;
      stopTimer();
      remainingMs = Math.max(0, (remainingMs ?? 0) - (Date.now() - startAt));
      startAt = null;
    },

    resume() {
      if (startAt !== null || remainingMs === null || remainingMs <= 0 || current === null) return;
      startTimer(remainingMs);
    },

    runAction() {
      const fn = current?.onAction;
      if (fn) fn();
      dismiss();
    },
  };
}

export const toasts = createToasts();
