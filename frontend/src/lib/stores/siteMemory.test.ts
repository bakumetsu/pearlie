import { describe, expect, it } from "vitest";
import { readSites, writeSites } from "./siteMemory";

function mem(initial?: string) {
  const data = new Map<string, string>();
  if (initial !== undefined) data.set("pearlie.search.sites", initial);
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
}

describe("siteMemory", () => {
  it("returns undefined when nothing is saved", () => {
    expect(readSites(mem())).toBeUndefined();
  });
  it("round-trips the pills, including none", () => {
    const s = mem();
    writeSites(["gelbooru", "rule34"], s);
    expect(readSites(s)).toEqual(["gelbooru", "rule34"]);
    writeSites([], s);
    expect(readSites(s)).toEqual([]);
  });
  it("drops unknown sites", () => {
    expect(readSites(mem("rule34,bogus"))).toEqual(["rule34"]);
  });
  it("survives blocked storage", () => {
    const bad = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); } };
    expect(readSites(bad)).toBeUndefined();
    expect(() => writeSites(["rule34"], bad)).not.toThrow();
  });
});
