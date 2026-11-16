// At most MAX_PLAYING grid GIFs play at once; the oldest one goes back to its still.
export const MAX_PLAYING = 6;

const playing: Array<() => void> = [];

/** Take a slot. `evict` runs when a newer tile needs it. Returns the release function. */
export function takeSlot(evict: () => void): () => void {
  playing.push(evict);
  while (playing.length > MAX_PLAYING) playing.shift()?.();
  return () => {
    const i = playing.indexOf(evict);
    if (i >= 0) playing.splice(i, 1);
  };
}

/** Slots in use (tests check that unmounted tiles give theirs back). */
export function slotsInUse(): number {
  return playing.length;
}

// Grid GIF preloads. A local GIF can be 20-120 MB: a load that leaves the screen mid-way would
// restart on every scroll and never finish. A started load runs to its end (the browser then has
// the file cached); only a load still queued is dropped. A few at once so the stills keep loading.
export const MAX_LOADING = 3;

const loading = new Set<HTMLImageElement>();
const queue: Array<() => void> = [];

function pump() {
  while (loading.size < MAX_LOADING && queue.length) queue.shift()?.();
}

/** Preload `url`; `done` runs once it loaded, unless cancelled. Returns the cancel function. */
export function preloadGif(url: string, done: () => void): () => void {
  let cancelled = false;
  let img: HTMLImageElement | null = null;
  const start = () => {
    const pre = (img = new Image());
    loading.add(pre);
    const end = (ok: boolean) => {
      pre.onload = null;
      pre.onerror = null;
      loading.delete(pre);
      pump();
      if (ok && !cancelled) done();
      else pre.src = "";
    };
    pre.onload = () => end(true);
    pre.onerror = () => end(false);
    pre.src = url;
  };
  queue.push(start);
  pump();
  return () => {
    cancelled = true;
    const i = queue.indexOf(start);
    if (i >= 0) queue.splice(i, 1);
    else if (img && !loading.has(img)) img.src = "";
  };
}

/** Forget every preload (tests). */
export function resetPreloads() {
  loading.clear();
  queue.length = 0;
}
