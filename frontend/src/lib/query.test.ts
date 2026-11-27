import { describe, it, expect } from "vitest";
import rows from "../../../backend/tests/fixtures/query_terms.json";
import {
  parseChip,
  nhentaiIdOf,
  splitInput,
  commitText,
  removeChipAt,
  removeLastChip,
  serialiseQuery,
  parseQuery,
  sectionsFor,
  parseSearchParams,
  buildSearchParams,
  webNeedsQuery,
  chipKind,
  chipLabel,
  chipRemoveLabel,
  hasOpenQuote,
  type Chip,
  type SearchState,
} from "./query";

describe("parseChip", () => {
  it("parses a plain value", () => {
    const c = parseChip("hello")!;
    expect(c).toEqual({ raw: "hello", exclude: false, scope: null, value: "hello" });
  });

  it("parses an exclude prefix", () => {
    const c = parseChip("-tag")!;
    expect(c).toEqual({ raw: "-tag", exclude: true, scope: null, value: "tag" });
  });

  it("parses a scope:value pair", () => {
    const c = parseChip("artist:foo")!;
    expect(c).toEqual({ raw: "artist:foo", exclude: false, scope: "artist", value: "foo" });
  });

  it("parses exclude + scope", () => {
    const c = parseChip("-artist:foo")!;
    expect(c).toEqual({ raw: "-artist:foo", exclude: true, scope: "artist", value: "foo" });
  });

  it("returns null for a lone dash", () => {
    expect(parseChip("-")).toBeNull();
  });

  it("keeps trailing colon as a plain value", () => {
    const c = parseChip("a:")!;
    expect(c).toEqual({ raw: "a:", exclude: false, scope: null, value: "a:" });
  });
});

describe("splitInput", () => {
  it("splits on spaces and commas, dropping empties", () => {
    expect(splitInput("a b,c  ,d")).toEqual(["a", "b", "c", "d"]);
    expect(splitInput("   , , ")).toEqual([]);
  });
});

describe("commitText", () => {
  it("dedupes by raw", () => {
    const base: Chip[] = [parseChip("a")!];
    expect(commitText(base, "a b").map((c) => c.raw)).toEqual(["a", "b"]);
  });

  it("parses a pasted string", () => {
    expect(commitText([], "a b,c").map((c) => c.value)).toEqual(["a", "b", "c"]);
  });
});

describe("chip removal", () => {
  it("removeChipAt drops the index", () => {
    const chips = [parseChip("a")!, parseChip("b")!, parseChip("c")!];
    expect(removeChipAt(chips, 1).map((c) => c.raw)).toEqual(["a", "c"]);
  });

  it("removeLastChip on empty stays empty", () => {
    expect(removeLastChip([])).toEqual([]);
  });
});

describe("serialiseQuery / parseQuery round trip", () => {
  it("round trips", () => {
    const chips = [parseChip("cat")!, parseChip("-dog")!, parseChip("artist:foo")!];
    expect(parseQuery(serialiseQuery(chips))).toEqual(chips);
  });
});

describe("sectionsFor", () => {
  it("resolves each pill", () => {
    expect(sectionsFor("all", ["nhentai"])).toEqual([
      "nhentai", "stash_images", "stash_videos", "stump_books",
    ]);
    expect(sectionsFor("all", ["gelbooru", "danbooru"])).toEqual([
      "gelbooru", "danbooru", "stash_images", "stash_videos", "stump_books",
    ]);
    expect(sectionsFor("images", [])).toEqual(["stash_images"]);
    expect(sectionsFor("videos", [])).toEqual(["stash_videos"]);
    expect(sectionsFor("books", [])).toEqual(["stump_books"]);
    expect(sectionsFor("web", ["gelbooru", "rule34"])).toEqual(["gelbooru", "rule34"]);
  });
});

describe("parseSearchParams", () => {
  it("defaults on missing params", () => {
    expect(parseSearchParams("")).toEqual({ chips: [], pill: "all", sites: ["danbooru"], all: true });
  });

  it("ignores an invalid src", () => {
    expect(parseSearchParams("?src=bogus").pill).toBe("all");
  });

  it("filters unknown sites", () => {
    expect(parseSearchParams("?sites=gelbooru,nope").sites).toEqual(["gelbooru"]);
  });

  it("treats empty sites as none", () => {
    expect(parseSearchParams("?sites=").sites).toEqual([]);
  });
});

describe("buildSearchParams", () => {
  const empty: SearchState = { chips: [], pill: "all", sites: ["danbooru"] };
  it("empty state is empty string", () => {
    expect(buildSearchParams(empty)).toBe("");
  });

  it("encodes q, src, sites", () => {
    const s: SearchState = {
      chips: [parseChip("cat")!, parseChip("artist:foo")!],
      pill: "web",
      sites: ["gelbooru", "rule34"],
    };
    expect(buildSearchParams(s)).toBe("?q=cat+artist%3Afoo&src=web&sites=gelbooru%2Crule34");
  });

  it("omits default sites", () => {
    const s: SearchState = { chips: [], pill: "web", sites: ["danbooru"] };
    expect(buildSearchParams(s)).toBe("?src=web");
  });

  it("round trips through parse", () => {
    const s: SearchState = {
      chips: [parseChip("artist:foo")!],
      pill: "images",
      sites: ["gelbooru"],
      all: false,
    };
    expect(parseSearchParams(buildSearchParams(s))).toEqual(s);
  });

  it("All: the first visit and all=1 start with All; a sites address does not", () => {
    expect(parseSearchParams("").all).toBe(true);
    expect(parseSearchParams("?all=1").all).toBe(true);
    expect(parseSearchParams("?sites=gelbooru").all).toBe(false);
    expect(parseSearchParams("?sites=").all).toBe(false);
  });

  it("All is written as all=1; without All the sites are always written", () => {
    expect(buildSearchParams({ chips: [], pill: "all", sites: ["danbooru"], all: true })).toBe("?all=1");
    expect(buildSearchParams({ chips: [], pill: "all", sites: ["danbooru"], all: false })).toBe("?sites=danbooru");
    const s: SearchState = { chips: [], pill: "all", sites: ["danbooru"], all: true };
    expect(parseSearchParams(buildSearchParams(s))).toEqual(s);
  });

  it("sectionsFor leaves the library rows out on an empty query", () => {
    expect(sectionsFor("all", ["danbooru"], true)).toEqual(["danbooru"]);
    expect(sectionsFor("all", ["danbooru"], false)).toEqual(["danbooru", "stash_images", "stash_videos", "stump_books"]);
  });
});

describe("webNeedsQuery", () => {
  it("true only when no chips", () => {
    expect(webNeedsQuery({ chips: [], pill: "web", sites: [] })).toBe(true);
    expect(webNeedsQuery({ chips: [parseChip("x")!], pill: "web", sites: [] })).toBe(false);
  });
});

describe("nhentaiIdOf", () => {
  it("accepts a plain number and an id: token", () => {
    expect(nhentaiIdOf("177013")).toBe("177013");
    expect(nhentaiIdOf(" id:177013 ")).toBe("177013");
    expect(nhentaiIdOf("ID:5")).toBe("5");
  });

  it("rejects everything else", () => {
    for (const t of ["", "0", "012", "cat", "id:", "id:abc", "-177013", "artist:1", "12 34", "1.5"]) {
      expect(nhentaiIdOf(t)).toBeNull();
    }
  });
});

describe("splitInput (shared table with the backend)", () => {
  for (const row of rows) {
    it(`splits ${JSON.stringify(row.text)}`, () => {
      expect(splitInput(row.text)).toEqual(row.tokens);
    });
  }
});

describe("title chips", () => {
  it("parses a quoted token as a title chip", () => {
    expect(parseChip('"big dragon"')).toEqual({
      raw: 'title:"big dragon"',
      exclude: false,
      scope: "title",
      value: "big dragon",
    });
  });

  it("parses title:value, quoted or not, and keeps underscores", () => {
    expect(parseChip("title:foo_bar")!.raw).toBe('title:"foo_bar"');
    expect(parseChip('title:"a b"')!.value).toBe("a b");
  });

  it("parses an excluded title and drops inner quotes", () => {
    const c = parseChip('-title:"a"b"')!;
    expect(c.exclude).toBe(true);
    expect(c.raw).toBe('-title:"ab"');
  });

  it("gives null for an empty title", () => {
    expect(parseChip('title:""')).toBeNull();
    expect(parseChip("title:")).toBeNull();
    expect(parseChip('""')).toBeNull();
  });

  it("keeps an unterminated quote as the rest of the text", () => {
    expect(commitText([], '"big dragon').map((c) => c.raw)).toEqual(['title:"big dragon"']);
  });

  it("merges duplicates by canonical raw", () => {
    const chips = commitText([], 'title:x "x" cat');
    expect(chips.map((c) => c.raw)).toEqual(['title:"x"', "cat"]);
  });

  it("round-trips through the URL query", () => {
    const chips = commitText([], 'a "b c" -title:"d e" artist:ruka');
    expect(parseQuery(serialiseQuery(chips))).toEqual(chips);
  });

  it("chipKind separates title, id and tag", () => {
    expect(chipKind(parseChip('"x"')!)).toBe("title");
    expect(chipKind(parseChip("id:5")!)).toBe("id");
    expect(chipKind(parseChip("artist:ruka")!)).toBe("tag");
  });

  it("labels like a tag chip, without quotes", () => {
    expect(chipLabel(parseChip('"big dragon"')!)).toBe("title:big dragon");
    expect(chipLabel(parseChip('-title:"x y"')!)).toBe("-title:x y");
    expect(chipLabel(parseChip("artist:ruka")!)).toBe("artist:ruka");
    expect(chipRemoveLabel(parseChip('"big dragon"')!)).toBe("Remove title big dragon");
  });

  it("hasOpenQuote is true for an odd number of quotes", () => {
    expect(hasOpenQuote('"big')).toBe(true);
    expect(hasOpenQuote('"big"')).toBe(false);
    expect(hasOpenQuote("")).toBe(false);
  });
});
