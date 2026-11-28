import { describe, it, expect } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins classes and lets the later Tailwind utility win", () => {
    expect(cn("p-2", false, "p-4", ["text-sm"])).toBe("p-4 text-sm");
  });
});
