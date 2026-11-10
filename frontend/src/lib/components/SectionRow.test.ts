import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(join(process.cwd(), "src/lib/components/SectionRow.svelte"), "utf8");

function rule(src: string, selector: string): string {
  const start = src.indexOf(selector + " {");
  const end = src.indexOf("}", start);
  return src.slice(start, end + 1);
}

describe("SectionRow", () => {
  it("strip is a horizontal scroll container", () => {
    const r = rule(source, ".strip");
    expect(r).toContain("overflow-x: auto");
    expect(r).toContain("min-width: 0");
  });

  it("cards are one seventh of the strip with a 120px minimum", () => {
    expect(source).toContain("flex: 0 0 max(120px, calc((100% - 6 * var(--s-2)) / 7))");
  });

  it("wrappers do not widen the page", () => {
    expect(rule(source, ".row")).toContain("min-width: 0");
    expect(rule(source, ".strip-wrap")).toContain("min-width: 0");
  });
});
