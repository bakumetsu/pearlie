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

  it("from 900 px the strip item size comes from railColumns via --cols", () => {
    expect(source).toContain("railColumns(");
    expect(source).toContain("style:--cols");
    expect(source).toContain("flex: 0 0 calc((100% - (var(--cols) - 1) * var(--s-2)) / var(--cols))");
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

  it("arrows are round translucent discs, 44px, shown on row hover or focus-visible", () => {
    const r = rule(source, ".arrow");
    expect(r).toContain("width: 44px");
    expect(r).toContain("height: 44px");
    expect(r).toContain("border-radius: 50%");
    expect(r).toContain("rgba(0, 0, 0,");
    expect(r).toContain("opacity: 0");
    expect(r).toContain("top: 50%");
    expect(source).toContain(".strip-wrap:hover .arrow {");
    expect(source).toContain(".arrow:focus-visible {");
    expect(rule(source, ".strip-wrap:hover .arrow")).toContain("opacity: 1");
  });

  it("arrows are hidden on touch devices", () => {
    const start = source.indexOf("@media (hover: none)");
    expect(start).toBeGreaterThan(-1);
    expect(source.slice(start, start + 80)).toContain(".arrow");
    expect(source.slice(start, start + 120)).toContain("display: none");
  });
});
