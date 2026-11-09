// Tests for the videoPreview store (T-36)
import { describe, it, expect, beforeEach } from "vitest";
import { videoPreview } from "./videoPreview.svelte";

describe("videoPreview", () => {
  beforeEach(() => videoPreview.reset());

  it("starts one key and reports it active", () => {
    videoPreview.start("a");
    expect(videoPreview.isActive("a")).toBe(true);
    expect(videoPreview.active).toBe("a");
  });

  it("keeps only one active key at a time", () => {
    videoPreview.start("a");
    videoPreview.start("b");
    expect(videoPreview.isActive("a")).toBe(false);
    expect(videoPreview.isActive("b")).toBe(true);
  });

  it("stop only clears the matching key", () => {
    videoPreview.start("a");
    videoPreview.stop("b");
    expect(videoPreview.isActive("a")).toBe(true);
    videoPreview.stop("a");
    expect(videoPreview.active).toBeNull();
  });
});
