export type TagObj = { name: string; scope?: string | null };

export function tagToString(t: TagObj): string {
  return t.scope ? `${t.scope}:${t.name}` : t.name;
}

export function stringToTag(s: string): TagObj {
  const idx = s.indexOf(":");
  if (idx > 0 && idx < s.length - 1) {
    return { name: s.slice(idx + 1), scope: s.slice(0, idx) };
  }
  return { name: s, scope: null };
}

export function parseTagInput(text: string): string[] {
  const parts = text.split(/[\s,]+/).map((s) => s.trim());
  const seen = new Set<string>();
  const result: string[] = [];
  for (const part of parts) {
    if (part === "") continue;
    const key = part.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(part);
  }
  return result;
}

export function addTags(current: string[], input: string): string[] {
  const parsed = parseTagInput(input);
  const existing = new Set(current.map((t) => t.toLowerCase()));
  const toAdd = parsed.filter((t) => !existing.has(t.toLowerCase()));
  if (toAdd.length === 0) return current;
  return [...current, ...toAdd];
}

export function removeTag(current: string[], tag: string): string[] {
  return current.filter((t) => t !== tag);
}
