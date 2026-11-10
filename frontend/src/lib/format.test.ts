// formatDuration tests (T-61)
import { describe, it, expect } from "vitest";
import { formatDuration } from "./format";

describe("formatDuration", () => {
  it("formats seconds under a minute", () => {
    expect(formatDuration(65)).toBe("1:05");
  });

  it("formats zero", () => {
    expect(formatDuration(0)).toBe("0:00");
  });

  it("formats hours with zero minutes and seconds", () => {
    expect(formatDuration(3600)).toBe("1:00:00");
  });

  it("formats hours, minutes, and seconds", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
  });

  it("floors fractional seconds", () => {
    expect(formatDuration(59.9)).toBe("0:59");
  });
});
