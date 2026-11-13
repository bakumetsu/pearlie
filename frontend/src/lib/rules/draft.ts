import type { components } from "../api/schema.gen";

export type RulesBody = components["schemas"]["RulesBody"];
export type RuleMapping = components["schemas"]["RuleMapping"];

export type Draft = {
  reject: string[];
  warn: string[];
  require: string[];
  mapping: RuleMapping[];
};

export type ListKey = "reject" | "warn" | "require";

const MAPPING_TARGETS: readonly string[] = [
  "stash_tag",
  "comicinfo:Tags",
  "comicinfo:Genre",
  "comicinfo:Writer",
  "comicinfo:Series",
];

export function draftFrom(body: RulesBody): Draft {
  return {
    reject: [...(body.reject ?? [])],
    warn: [...(body.warn ?? [])],
    require: [...(body.require ?? [])],
    mapping: body.mapping ? body.mapping.map((m) => ({ ...m })) : [],
  };
}

export function normalizeTag(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.startsWith("scope:")) {
    return "scope:" + trimmed.slice(6).toLowerCase().replace(/[\s_-]+/g, "_");
  }
  return trimmed.toLowerCase().replace(/[\s_-]+/g, "_");
}

export function addTag(list: string[], raw: string): string[] {
  const tag = normalizeTag(raw);
  if (!tag || list.includes(tag)) return [...list];
  return [...list, tag];
}

export function removeTag(list: string[], tag: string): string[] {
  return list.filter((t) => t !== tag);
}

export function addMapping(
  m: RuleMapping[],
  pattern: string,
  to: RuleMapping["to"],
): RuleMapping[] {
  const p = normalizeTag(pattern);
  if (!p) return [...m];
  if (m.some((x) => x.pattern === p && x.to === to)) return [...m];
  return [...m, { pattern: p, to }];
}

export function removeMapping(m: RuleMapping[], index: number): RuleMapping[] {
  return m.filter((_, i) => i !== index);
}

export function setMappingTarget(
  m: RuleMapping[],
  index: number,
  to: RuleMapping["to"],
): RuleMapping[] {
  return m.map((x, i) => (i === index ? { ...x, to } : x));
}

function listsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sa = [...a].sort();
  const sb = [...b].sort();
  return sa.every((v, i) => v === sb[i]);
}

export function isDirty(base: Draft, draft: Draft): boolean {
  if (!listsEqual(base.reject, draft.reject)) return true;
  if (!listsEqual(base.warn, draft.warn)) return true;
  if (!listsEqual(base.require, draft.require)) return true;
  if (base.mapping.length !== draft.mapping.length) return true;
  for (let i = 0; i < base.mapping.length; i++) {
    if (base.mapping[i].pattern !== draft.mapping[i].pattern) return true;
    if (base.mapping[i].to !== draft.mapping[i].to) return true;
  }
  return false;
}

export type DraftDiff = {
  added: Record<ListKey, string[]>;
  removed: Record<ListKey, string[]>;
  mappingAdded: RuleMapping[];
  mappingRemoved: RuleMapping[];
};

function listDiff(base: string[], draft: string[]) {
  const bSet = new Set(base);
  const dSet = new Set(draft);
  return {
    added: draft.filter((x) => !bSet.has(x)),
    removed: base.filter((x) => !dSet.has(x)),
  };
}

export function diffDraft(base: Draft, draft: Draft): DraftDiff {
  const rJ = listDiff(base.reject, draft.reject);
  const rW = listDiff(base.warn, draft.warn);
  const rR = listDiff(base.require, draft.require);

  const key = (m: RuleMapping) => `${m.pattern}\u0000${m.to}`;
  const baseKeys = new Set(base.mapping.map(key));
  const draftKeys = new Set(draft.mapping.map(key));

  return {
    added: { reject: rJ.added, warn: rW.added, require: rR.added },
    removed: { reject: rJ.removed, warn: rW.removed, require: rR.removed },
    mappingAdded: draft.mapping.filter((m) => !baseKeys.has(key(m))),
    mappingRemoved: base.mapping.filter((m) => !draftKeys.has(key(m))),
  };
}

export function diffSummary(d: DraftDiff): string {
  const parts: string[] = [];
  const push = (n: number, label: string) => {
    if (n > 0) parts.push(`+${n} ${label}`);
  };
  const pushNeg = (n: number, label: string) => {
    if (n > 0) parts.push(`-${n} ${label}`);
  };

  push(d.added.reject.length, "reject");
  pushNeg(d.removed.reject.length, "reject");
  push(d.added.warn.length, "warn");
  pushNeg(d.removed.warn.length, "warn");
  push(d.added.require.length, "require");
  pushNeg(d.removed.require.length, "require");
  push(d.mappingAdded.length, "mapping");
  pushNeg(d.mappingRemoved.length, "mapping");

  return parts.length ? parts.join(", ") : "No changes";
}

export function toPut(
  version: number,
  draft: Draft,
): components["schemas"]["RulesPut"] {
  return {
    version,
    reject: [...draft.reject],
    warn: [...draft.warn],
    require: [...draft.require],
    mapping: draft.mapping.map((m) => ({ ...m })),
  };
}

export function exportJson(body: RulesBody): string {
  const rest: Record<string, unknown> = { ...body }; delete rest.base_list;
  return JSON.stringify(rest, null, 2);
}

export type ImportResult =
  | { ok: true; draft: Draft }
  | { ok: false; error: string };

function asStringArray(value: unknown): string[] | null {
  if (value == null) return [];
  if (!Array.isArray(value)) return null;
  if (!value.every((v) => typeof v === "string")) return null;
  return value;
}

export function parseImport(text: string): ImportResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, error: "Not valid JSON" };
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { ok: false, error: "Must be a JSON object" };
  }

  const obj = parsed as Record<string, unknown>;

  const rawReject = asStringArray(obj.reject);
  if (rawReject === null) return { ok: false, error: "reject must be a list of text" };
  const rawWarn = asStringArray(obj.warn);
  if (rawWarn === null) return { ok: false, error: "warn must be a list of text" };
  const rawRequire = asStringArray(obj.require);
  if (rawRequire === null) return { ok: false, error: "require must be a list of text" };

  const mapping: RuleMapping[] = [];
  if (obj.mapping != null) {
    if (!Array.isArray(obj.mapping)) {
      return { ok: false, error: "mapping must be a list of {pattern, to}" };
    }
    for (let i = 0; i < obj.mapping.length; i++) {
      const item = obj.mapping[i] as Record<string, unknown>;
      if (typeof item !== "object" || item === null) {
        return { ok: false, error: `mapping[${i}] must be an object` };
      }
      if (typeof item.pattern !== "string") {
        return { ok: false, error: `mapping[${i}].pattern must be text` };
      }
      if (typeof item.to !== "string" || !MAPPING_TARGETS.includes(item.to)) {
        return {
          ok: false,
          error: `mapping[${i}].to must be one of ${MAPPING_TARGETS.join(", ")}`,
        };
      }
      mapping.push({ pattern: normalizeTag(item.pattern), to: item.to as RuleMapping["to"] });
    }
  }

  const dedupe = (arr: string[]) => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const tag of arr) {
      const n = normalizeTag(tag);
      if (n && !seen.has(n)) {
        seen.add(n);
        out.push(n);
      }
    }
    return out;
  };

  return {
    ok: true,
    draft: {
      reject: dedupe(rawReject),
      warn: dedupe(rawWarn),
      require: dedupe(rawRequire),
      mapping,
    },
  };
}

