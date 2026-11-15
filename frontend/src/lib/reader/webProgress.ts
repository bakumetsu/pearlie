const KEY = "pearlie.webread.v1";
const MAX = 200;

type Entry = { page: number; ts: number };
type Store = Record<string, Entry>;

function read(): Store {
  try {
    const raw = localStorage.getItem(KEY);
    const v = raw ? JSON.parse(raw) : {};
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Store) : {};
  } catch {
    return {};
  }
}

function write(s: Store): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // private window or full storage: progress is best effort
  }
}

export function getWebPage(key: string): number | null {
  const e = read()[key];
  return e && Number.isInteger(e.page) ? e.page : null;
}

export function setWebPage(key: string, page: number, count: number, now = Date.now()): void {
  const s = read();
  if (page <= 1 || page >= count) {
    if (!(key in s)) return;
    delete s[key];
  } else {
    s[key] = { page, ts: now };
    const keys = Object.keys(s);
    if (keys.length > MAX) {
      keys.sort((a, b) => (s[a].ts ?? 0) - (s[b].ts ?? 0));
      for (const k of keys.slice(0, keys.length - MAX)) delete s[k];
    }
  }
  write(s);
}
