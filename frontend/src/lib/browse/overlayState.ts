// overlayState: parse and build the open=image:<id> URL param for the wall overlay

export function parseOpen(query: URLSearchParams): string | null {
  const raw = query.get("open");
  if (raw === null) return null;
  if (!raw.startsWith("image:")) return null;
  const id = raw.slice(6);
  if (id.length === 0) return null;
  if (/[:\s]/.test(id)) return null;
  return id;
}

export function openKey(id: string): string {
  return `image:${id}`;
}

export function withOpen(query: URLSearchParams, key: string | null): string {
  const next = new URLSearchParams(query.toString());
  if (key !== null && key.startsWith("image:")) {
    const id = key.slice(6);
    if (id.length > 0 && !/[:\s]/.test(id)) {
      next.set("open", key);
    } else {
      next.delete("open");
    }
  } else {
    next.delete("open");
  }
  return next.toString();
}
