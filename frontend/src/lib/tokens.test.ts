import { describe, it, expect } from "vitest";

const svelte = import.meta.glob("/src/**/*.svelte", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

describe("text colour tokens", () => {
  it("every var(--text-*) used in a .svelte file is defined in tokens.css", async () => {
    // vitest strips CSS imports, so read tokens.css from disk (no @types/node here)
    const fs = await import(/* @vite-ignore */ "node:" + "fs");
    const css: string = fs.readFileSync("src/lib/tokens.css", "utf-8");
    expect(css.length).toBeGreaterThan(0);
    const defined = new Set([...css.matchAll(/(--text[a-z0-9-]*)\s*:/g)].map((m) => m[1]));
    const used: string[] = [];
    for (const [file, text] of Object.entries(svelte)) {
      for (const m of text.matchAll(/var\((--text[a-z0-9-]*)/g)) {
        if (!defined.has(m[1])) used.push(`${file}: ${m[1]}`);
      }
    }
    expect(Object.keys(svelte).length).toBeGreaterThan(0);
    expect(used).toEqual([]);
  });
});
