import source from "./ResultsGrid.svelte?raw";
import { describe, expect, it } from "vitest";

// jsdom does not run layout. The windowed cells carry class "vcell {mode}", so a bare `.grid`, `.list` or
// `.masonry` rule would also hit them (masonry: a flex row, so the tile shrank to 0 x 0 and See all was blank).
describe("ResultsGrid css", () => {
  const css = source.split("<style>")[1] ?? "";

  it.each(["grid", "list", "masonry"])("flow container rule .%s is scoped to the direct child of .rg", (name) => {
    const rule = new RegExp(String.raw`^\s*[^{/]*\.` + name + String.raw`\b[^{]*\{`);
    const hits = css.split("\n").filter((l: string) => rule.test(l) && !l.includes("vcell"));
    expect(hits.length).toBeGreaterThan(0);
    for (const r of hits) expect(r.trim().startsWith(".rg >")).toBe(true);
  });
});
