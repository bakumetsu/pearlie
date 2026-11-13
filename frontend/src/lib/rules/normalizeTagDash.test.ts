import { describe, it, expect } from "vitest";
import { normalizeTag, addTag } from "./draft";

describe("normalizeTag folds like the backend (space, underscore, dash)", () => {
  it("folds dashes to underscores", () => {
    expect(normalizeTag("Blue-Hair")).toBe("blue_hair");
    expect(normalizeTag("blue - hair")).toBe("blue_hair");
    expect(normalizeTag("scope:Blue-Hair")).toBe("scope:blue_hair");
  });
  it("collapses mixed separators", () => {
    expect(normalizeTag("a _- b")).toBe("a_b");
  });
  it("dash and underscore forms are the same tag", () => {
    expect(addTag(["blue_hair"], "blue-hair")).toEqual(["blue_hair"]);
  });
});
