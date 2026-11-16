import { describe, it, expect } from "vitest";
import src from "./SeeAll.svelte?raw";

describe("SeeAll sticky bar scale", () => {
  it("defines one --bar-scale var and scales the header spacing with it", () => {
    expect(src).toMatch(/--bar-scale:\s*0\.(80|85|95)\s*;/);
    expect(src).toMatch(/padding:\s*calc\(var\(--s-4\) \* var\(--bar-scale\)\) 0/);
    expect(src).toMatch(/\.controls[^}]*margin-top:\s*calc\(var\(--s-4\) \* var\(--bar-scale\)\)/);
  });

  it("keeps the 44 px hit area on the back button", () => {
    expect(src).toMatch(/\.back-btn\s*\{[^}]*min-width:\s*44px;[^}]*min-height:\s*44px/);
  });
});
