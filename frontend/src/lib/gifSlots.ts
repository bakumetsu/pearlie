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
