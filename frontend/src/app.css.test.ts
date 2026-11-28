import { describe, it, expect } from "vitest";

describe("app.css base", () => {
  it("keeps preflight off and scopes the reset to .ui-root", async () => {
    // vitest serves CSS empty, so read it from disk (no @types/node here)
    const fs = await import(/* @vite-ignore */ "node:" + "fs");
    const css: string = fs.readFileSync("src/app.css", "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).not.toMatch(/@import\s+["']tailwindcss["']/);
    expect(css).not.toMatch(/tailwindcss\/preflight/);
    const base = css.slice(css.indexOf("@layer base"));
    const selectors = [...base.matchAll(/^\s*(:where\([^{]*?)\{/gm)].map((m) => m[1]);
    expect(selectors.length).toBeGreaterThan(5);
    for (const s of selectors) expect(s).toContain(".ui-root");
  });
  it("defines every Ink Top token under .ui-root", async () => {
    const fs = await import(/* @vite-ignore */ "node:" + "fs");
    const css: string = fs.readFileSync("src/app.css", "utf-8");
    const block = css.slice(css.indexOf(".ui-root {"), css.indexOf(":root[data-theme"));
    for (const n of ["background", "foreground", "card", "popover", "muted", "muted-foreground", "border", "input", "ring", "primary", "primary-foreground", "accent", "destructive", "ok", "warn", "progress", "scrim"]) {
      expect(block).toMatch(new RegExp(`--${n}:`));
    }
  });
  it("leaves the old token names in tokens.css with their old values", async () => {
    const fs = await import(/* @vite-ignore */ "node:" + "fs");
    const css: string = fs.readFileSync("src/lib/tokens.css", "utf-8");
    expect(css).toContain("--bg: #121214;");
    expect(css).toContain("--accent: #7FB0FF;");
  });
});
