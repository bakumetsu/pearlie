import type { Mode, Fit, Dir } from "./pages";

export type Settings = { mode: Mode | null; fit: Fit; dir: Dir; zoom: number };

export const SETTINGS_KEY = "pearlie.reader.settings";
export const OLD_MODE_KEY = "pearlie.reader.mode";

export const DEFAULT_SETTINGS: Settings = { mode: null, fit: "both", dir: "ltr", zoom: 100 };

function isMode(value: unknown): value is Mode {
  return value === "single" || value === "spread" || value === "scroll";
}

function isFit(value: unknown): value is Fit {
  return value === "width" || value === "height" || value === "both" || value === "actual";
}

function isDir(value: unknown): value is Dir {
  return value === "ltr" || value === "rtl";
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function zoomFrom(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.min(Math.max(Math.round(value), 50), 300);
  }
  return DEFAULT_SETTINGS.zoom;
}

function fromRaw(raw: string | null): Settings | null {
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!isPlainObject(parsed)) return null;
    return {
      mode: isMode(parsed.mode) ? parsed.mode : null,
      fit: isFit(parsed.fit) ? parsed.fit : DEFAULT_SETTINGS.fit,
      dir: isDir(parsed.dir) ? parsed.dir : DEFAULT_SETTINGS.dir,
      zoom: zoomFrom(parsed.zoom),
    };
  } catch {
    return null;
  }
}

function fromOldRaw(oldRaw: string | null): Settings | null {
  if (oldRaw === null) return null;
  try {
    const parsed = JSON.parse(oldRaw);
    if (!isPlainObject(parsed)) return null;
    return {
      mode: parsed.spread === true ? "spread" : "single",
      fit: isFit(parsed.fit) ? parsed.fit : DEFAULT_SETTINGS.fit,
      dir: parsed.rtl === true ? "rtl" : "ltr",
      zoom: DEFAULT_SETTINGS.zoom,
    };
  } catch {
    return null;
  }
}

function globalStorage(): Pick<Storage, "getItem" | "setItem"> | undefined {
  return (globalThis as { localStorage?: Pick<Storage, "getItem" | "setItem"> }).localStorage;
}

export function parseSettings(raw: string | null, oldRaw: string | null): Settings {
  return fromRaw(raw) ?? fromOldRaw(oldRaw) ?? { ...DEFAULT_SETTINGS };
}

export function loadSettings(storage?: Pick<Storage, "getItem">): Settings {
  const store = storage ?? globalStorage();
  if (!store) return { ...DEFAULT_SETTINGS };
  try {
    return parseSettings(store.getItem(SETTINGS_KEY), store.getItem(OLD_MODE_KEY));
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(s: Settings, storage?: Pick<Storage, "setItem">): void {
  const store = storage ?? globalStorage();
  if (!store) return;
  try {
    store.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    // Ignore storage failures.
  }
}
