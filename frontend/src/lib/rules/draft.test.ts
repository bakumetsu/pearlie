import { describe, it, expect } from "vitest";
import {
  draftFrom,
  normalizeTag,
  addTag,
  removeTag,
  addMapping,
  removeMapping,
  setMappingTarget,
  isDirty,
  diffDraft,
  diffSummary,
  toPut,
  exportJson,
  parseImport,
  type Draft,
  type RulesBody,
  type RuleMapping,
} from "./draft";

function makeBody(over: Partial<RulesBody> = {}): RulesBody {
  return {
    reject: ["a", "b"],
    warn: ["c"],
    require: ["d"],
    mapping: [{ pattern: "x", to: "stash_tag" }],
    ...over,
  } as RulesBody;
}

function makeDraft(over: Partial<Draft> = {}): Draft {
  return {
    reject: ["a", "b"],
    warn: ["c"],
    require: ["d"],
    mapping: [{ pattern: "x", to: "stash_tag" }],
    ...over,
  };
}

describe("draftFrom", () => {
  it("deep copies arrays and mapping entries", () => {
    const body = makeBody();
    const d = draftFrom(body);
    expect(d).toEqual(body);

    // mutate original – draft unaffected
    body.reject!.push("z");
    body.mapping![0].pattern = "changed";
    expect(d.reject).toEqual(["a", "b"]);
    expect(d.mapping[0].pattern).toBe("x");
  });

  it("missing arrays become []", () => {
    const d = draftFrom({} as RulesBody);
    expect(d.reject).toEqual([]);
    expect(d.warn).toEqual([]);
    expect(d.require).toEqual([]);
    expect(d.mapping).toEqual([]);
  });
});

describe("normalizeTag", () => {
  it("trims, lowercases, collapses whitespace", () => {
    expect(normalizeTag("Blue Hair")).toBe("blue_hair");
    expect(normalizeTag("  hello   world  ")).toBe("hello_world");
  });

  it("keeps scope: prefix", () => {
    expect(normalizeTag("scope:Blue Hair")).toBe("scope:blue_hair");
  });

  it("empty string stays empty", () => {
    expect(normalizeTag("")).toBe("");
  });
});

describe("addTag / removeTag", () => {
  it("adds a normalized tag", () => {
    expect(addTag(["a"], "  B ")).toEqual(["a", "b"]);
  });

  it("duplicate returns same contents", () => {
    expect(addTag(["a", "b"], "b")).toEqual(["a", "b"]);
  });

  it("empty tag returns same contents", () => {
    expect(addTag(["a"], "   ")).toEqual(["a"]);
  });

  it("removeTag removes by value", () => {
    expect(removeTag(["a", "b", "c"], "b")).toEqual(["a", "c"]);
  });

  it("removeTag on missing tag is no-op", () => {
    expect(removeTag(["a"], "z")).toEqual(["a"]);
  });
});

describe("mapping helpers", () => {
  it("addMapping normalizes pattern and appends", () => {
    const m: RuleMapping[] = [];
    expect(addMapping(m, "  Blue Hair ", "stash_tag")).toEqual([
      { pattern: "blue_hair", to: "stash_tag" },
    ]);
  });

  it("addMapping ignores empty pattern", () => {
    const m: RuleMapping[] = [{ pattern: "x", to: "stash_tag" }];
    expect(addMapping(m, "  ", "stash_tag")).toEqual(m);
  });

  it("addMapping ignores identical pattern+to", () => {
    const m: RuleMapping[] = [{ pattern: "x", to: "stash_tag" }];
    expect(addMapping(m, "x", "stash_tag")).toEqual(m);
  });

  it("removeMapping removes by index", () => {
    const m: RuleMapping[] = [
      { pattern: "a", to: "stash_tag" },
      { pattern: "b", to: "stash_tag" },
    ];
    expect(removeMapping(m, 0)).toEqual([{ pattern: "b", to: "stash_tag" }]);
  });

  it("setMappingTarget changes only the target at index", () => {
    const m: RuleMapping[] = [
      { pattern: "a", to: "stash_tag" },
      { pattern: "b", to: "stash_tag" },
    ];
    expect(setMappingTarget(m, 1, "comicinfo:Tags")).toEqual([
      { pattern: "a", to: "stash_tag" },
      { pattern: "b", to: "comicinfo:Tags" },
    ]);
  });
});

describe("isDirty", () => {
  it("identical drafts are clean", () => {
    expect(isDirty(makeDraft(), makeDraft())).toBe(false);
  });

  it("list order is ignored", () => {
    const a = makeDraft({ reject: ["a", "b", "c"] });
    const b = makeDraft({ reject: ["c", "a", "b"] });
    expect(isDirty(a, b)).toBe(false);
  });

  it("mapping order matters", () => {
    const a = makeDraft({
      mapping: [
        { pattern: "x", to: "stash_tag" },
        { pattern: "y", to: "stash_tag" },
      ],
    });
    const b = makeDraft({
      mapping: [
        { pattern: "y", to: "stash_tag" },
        { pattern: "x", to: "stash_tag" },
      ],
    });
    expect(isDirty(a, b)).toBe(true);
  });

  it("different tag detected", () => {
    const a = makeDraft();
    const b = makeDraft({ reject: ["a"] });
    expect(isDirty(a, b)).toBe(true);
  });
});

describe("diffDraft + diffSummary", () => {
  it("no changes", () => {
    const d = diffDraft(makeDraft(), makeDraft());
    expect(diffSummary(d)).toBe("No changes");
  });

  it("detects added and removed tags", () => {
    const base = makeDraft({ reject: ["a", "b"], warn: ["c"] });
    const next = makeDraft({ reject: ["a", "d"], warn: ["c", "e"] });
    const diff = diffDraft(base, next);
    expect(diff.added.reject).toEqual(["d"]);
    expect(diff.removed.reject).toEqual(["b"]);
    expect(diff.added.warn).toEqual(["e"]);
    expect(diff.removed.warn).toEqual([]);
    expect(diffSummary(diff)).toBe("+1 reject, -1 reject, +1 warn");
  });

  it("detects mapping changes", () => {
    const base = makeDraft({
      mapping: [{ pattern: "x", to: "stash_tag" }],
    });
    const next = makeDraft({
      mapping: [
        { pattern: "x", to: "stash_tag" },
        { pattern: "y", to: "comicinfo:Tags" },
      ],
    });
    const diff = diffDraft(base, next);
    expect(diff.mappingAdded).toEqual([{ pattern: "y", to: "comicinfo:Tags" }]);
    expect(diff.mappingRemoved).toEqual([]);
    expect(diffSummary(diff)).toBe("+1 mapping");
  });
});

describe("toPut", () => {
  it("produces the put shape", () => {
    const d = makeDraft();
    const put = toPut(7, d);
    expect(put).toEqual({
      version: 7,
      reject: ["a", "b"],
      warn: ["c"],
      require: ["d"],
      mapping: [{ pattern: "x", to: "stash_tag" }],
    });
  });
});

describe("exportJson", () => {
  it("omits base_list and uses 2-space indent", () => {
    const body = { base_list: ["x"], reject: ["a"], warn: [], require: [], mapping: [] } as unknown as RulesBody;
    const json = exportJson(body);
    expect(json).not.toContain("base_list");
    expect(JSON.parse(json)).toEqual({ reject: ["a"], warn: [], require: [], mapping: [] });
    // 2-space indent check
    expect(json).toContain('\n  "reject"');
  });

  it("round-trips through parseImport", () => {
    const body = makeBody();
    const json = exportJson(body);
    const res = parseImport(json);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.draft.reject).toEqual(["a", "b"]);
      expect(res.draft.warn).toEqual(["c"]);
      expect(res.draft.require).toEqual(["d"]);
      expect(res.draft.mapping).toEqual([{ pattern: "x", to: "stash_tag" }]);
    }
  });
});

describe("parseImport", () => {
  it("bad JSON", () => {
    const res = parseImport("{oops");
    expect(res).toEqual({ ok: false, error: "Not valid JSON" });
  });

  it("array instead of object", () => {
    const res = parseImport("[1,2,3]");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toMatch(/object/i);
  });

  it("reject with a number", () => {
    const res = parseImport(JSON.stringify({ reject: [1] }));
    expect(res).toEqual({ ok: false, error: "reject must be a list of text" });
  });

  it("mapping with bad to", () => {
    const res = parseImport(
      JSON.stringify({ mapping: [{ pattern: "x", to: "bogus" }] }),
    );
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toContain("mapping[0].to");
  });

  it("success with missing keys", () => {
    const res = parseImport("{}");
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.draft).toEqual({ reject: [], warn: [], require: [], mapping: [] });
    }
  });

  it("normalizes and dedupes tags", () => {
    const res = parseImport(
      JSON.stringify({ reject: ["Blue Hair", "blue hair", "blue_hair"] }),
    );
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.draft.reject).toEqual(["blue_hair"]);
  });

  it("ignores unknown top-level keys", () => {
    const res = parseImport(
      JSON.stringify({ reject: ["a"], unknown_field: 42 }),
    );
    expect(res.ok).toBe(true);
  });
});

