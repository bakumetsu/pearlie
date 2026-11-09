import { describe, it, expect } from "vitest";
import { expiresLabel } from "./format";

const NOW = 1_700_000_000_000;

describe("expiresLabel", () => {
  it("30 min → 'Expires in under 1 h'", () => {
    const ts = new Date(NOW + 30 * 60_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in under 1 h");
  });

  it("past → 'Expired'", () => {
    const ts = new Date(NOW - 1_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expired");
  });

  it("47 h → 'Expires in 47 h'", () => {
    const ts = new Date(NOW + 47 * 3_600_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in 47 h");
  });

  it("48 h → 'Expires in 2 d'", () => {
    const ts = new Date(NOW + 48 * 3_600_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in 2 d");
  });

  it("6 days → 'Expires in 6 d'", () => {
    const ts = new Date(NOW + 6 * 86_400_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in 6 d");
  });

  it("invalid string → ''", () => {
    expect(expiresLabel("not-a-date", NOW)).toBe("");
  });
});
