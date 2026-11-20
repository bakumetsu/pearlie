import library from "../routes/Library.svelte?raw";
import queue from "../routes/Queue.svelte?raw";
import rules from "../routes/Rules.svelte?raw";
import search from "../routes/Search.svelte?raw";
import seeAll from "../routes/SeeAll.svelte?raw";
import trash from "../routes/Trash.svelte?raw";
import bookPage from "./book/BookPage.svelte?raw";
import { describe, expect, it } from "vitest";

// jsdom does not run layout, so the page-width contract (D-41) is checked on the CSS text of each page.
// (vitest serves tokens.css empty, so the token values are not asserted here.)
const pages = { library, queue, rules, search, seeAll, trash, bookPage };

describe("page width tokens", () => {
  it.each(Object.entries(pages))("%s has no width cap and uses the gutter", (_name, src) => {
    const css = src.split("<style>")[1] ?? "";
    expect(css).not.toContain("--content-max");
    expect(css).not.toMatch(/max-width:\s*720px/);
    expect(css).toContain("var(--gutter)");
  });
});
