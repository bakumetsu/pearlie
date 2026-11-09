import type { Kind } from "../api/client";

export type Hub = "all" | "stash" | "komga";

export const HUBS: { id: Hub; label: string; kinds: Kind[] | null }[] = [
  { id: "all", label: "All", kinds: null },
  { id: "stash", label: "Stash", kinds: ["images", "videos"] },
  { id: "komga", label: "Komga", kinds: ["series", "books"] },
];

export const HUB_KEY = "pearlie.library.hub";

export function isHub(v: unknown): v is Hub {
  return v === "all" || v === "stash" || v === "komga";
}

function globalStorage(): Pick<Storage, "getItem" | "setItem"> | undefined {
  return (globalThis as { localStorage?: Pick<Storage, "getItem" | "setItem"> }).localStorage;
}

export function loadHub(storage?: Pick<Storage, "getItem">): Hub {
  const store = storage ?? globalStorage();
  if (!store) return "all";
  try {
    const raw = store.getItem(HUB_KEY);
    return isHub(raw) ? raw : "all";
  } catch {
    return "all";
  }
}

export function saveHub(hub: Hub, storage?: Pick<Storage, "setItem">): void {
  const store = storage ?? globalStorage();
  if (!store) return;
  try {
    store.setItem(HUB_KEY, hub);
  } catch {
    // Ignore storage failures.
  }
}

export function hubKinds(hub: Hub, all: Kind[]): Kind[] {
  const entry = HUBS.find((h) => h.id === hub);
  if (!entry || entry.kinds === null) return [...all];
  const set = new Set(entry.kinds);
  return all.filter((k) => set.has(k));
}
