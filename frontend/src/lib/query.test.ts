import { describe, it, expect } from "vitest";
import {
  parseChip,
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
    const q = [parseChip("x")!];
    expect(sectionsFor("all", ["danbooru"], q)).toEqual([
      "stash_images", "stash_videos", "komga_books", "danbooru",
    ]);
    expect(sectionsFor("all", ["danbooru"], [])).toEqual([
      "danbooru", "stash_images", "stash_videos", "komga_books",
    ]);
    expect(sectionsFor("images", [], q)).toEqual(["stash_images"]);
    expect(sectionsFor("videos", [], q)).toEqual(["stash_videos"]);
    expect(sectionsFor("books", [], q)).toEqual(["komga_books"]);
    expect(sectionsFor("web", ["gelbooru", "rule34"], q)).toEqual(["gelbooru", "rule34"]);
  });
});

describe("parseSearchParams", () => {
  it("defaults on missing params", () => {
    expect(parseSearchParams("")).toEqual({ chips: [], pill: "all", sites: ["danbooru"] });
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
    };
    expect(parseSearchParams(buildSearchParams(s))).toEqual(s);
  });
});

describe("webNeedsQuery", () => {
  it("true only when no chips", () => {
    expect(webNeedsQuery({ chips: [], pill: "web", sites: [] })).toBe(true);
    expect(webNeedsQuery({ chips: [parseChip("x")!], pill: "web", sites: [] })).toBe(false);
  });
});
