import { describe, it, expect } from "vitest";
import source from "./SectionRow.svelte?raw";

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

  it("See all is an arrow-right icon link with a label and a 44px target", () => {
    expect(source).toContain('aria-label="See all"');
    expect(source).toContain('<Icon name="arrow-right"');
    expect(source).not.toContain(">See all<");
    const r = rule(source, ".see-all");
    expect(r).toContain("min-width: 44px");
    expect(r).toContain("min-height: 44px");
  });
});
