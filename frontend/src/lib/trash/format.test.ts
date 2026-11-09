import { describe, it, expect } from "vitest";
import { expiresLabel } from "./format";

const NOW = 1_700_000_000_000;

describe("expiresLabel", () => {
  it("30 min → 'Expires today'", () => {
    const ts = new Date(NOW + 30 * 60_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires today");
  });

  it("past → 'Expired'", () => {
    const ts = new Date(NOW - 1_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expired");
  });

  it("23 h → 'Expires today'", () => {
    const ts = new Date(NOW + 23 * 3_600_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires today");
  });

  it("47 h → 'Expires in 1 day'", () => {
    const ts = new Date(NOW + 47 * 3_600_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in 1 day");
  });

  it("48 h → 'Expires in 2 days'", () => {
    const ts = new Date(NOW + 48 * 3_600_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in 2 days");
  });

  it("6 days → 'Expires in 6 days'", () => {
    const ts = new Date(NOW + 6 * 86_400_000).toISOString();
    expect(expiresLabel(ts, NOW)).toBe("Expires in 6 days");
  });

  it("invalid string → ''", () => {
    expect(expiresLabel("not-a-date", NOW)).toBe("");
  });
});
