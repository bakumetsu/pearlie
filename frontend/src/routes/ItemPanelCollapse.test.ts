// Item page: the panel collapse slide keeps padding, border and overflow fixed (T-116).
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";

const css = readFileSync("src/routes/Item.svelte", "utf8");

function rule(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start).toBeGreaterThan(-1);
  return css.slice(start, css.indexOf("}", start));
}

describe("item panel collapse css", () => {
  it("keeps a fixed panel width so content does not re-wrap", () => {
    const r = rule("  .panel");
    expect(r).toContain("width: 360px");
    expect(r).toContain("min-width: 360px");
  });

  it("does not snap padding, border or overflow when collapsed on desktop", () => {
    const r = rule(".body.collapsed:not(.phone) .panel");
    expect(r).not.toMatch(/padding|border|overflow/);
    expect(r).toContain("visibility: hidden");
    expect(r).toContain("visibility 0s linear 250ms");
  });

  it("animates the grid column over 250ms and the phone panel by transform", () => {
    expect(rule("  .body").replace(/\s+/g, " ")).toContain("transition: grid-template-columns 250ms ease");
    expect(rule(".body.phone.collapsed .panel")).toContain("transform: translateX(100%)");
    expect(rule(".body.phone .panel")).toContain("min-width: 0");
  });

  it("keeps the reduced-motion instant toggle", () => {
    const i = css.indexOf("@media (prefers-reduced-motion: reduce)");
    expect(i).toBeGreaterThan(-1);
    const block = css.slice(i);
    expect(block).toContain(".body.collapsed:not(.phone) .panel");
    expect(block).toContain("transition: none");
  });
});
