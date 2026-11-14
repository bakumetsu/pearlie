import { describe, it, expect, vi } from "vitest";
import type { WebItem } from "../api/client";
import { saveWebItem, saveStateFor, savedHrefFor, settleQueued } from "./saveFlow";
import type { Job } from "../jobs/group";

const item = { source: "nhentai", post_id: "1" } as WebItem;

function deps(answer: unknown, result: unknown) {
  return {
    ask: vi.fn(async () => answer as never),
    save: vi.fn(async () => result as never),
    toast: vi.fn(),
  };
}

describe("saveWebItem", () => {
  it("does nothing when the placement sheet is closed", async () => {
    const d = deps(null, { result: "queued" });
    await saveWebItem(d, item);
    expect(d.save).not.toHaveBeenCalled();
    expect(d.toast).not.toHaveBeenCalled();
  });

  it("saves with the chosen placement and toasts the queue", async () => {
    const d = deps({ placement: { kind: "series" } }, { result: "queued" });
    await saveWebItem(d, item);
    expect(d.save).toHaveBeenCalledWith(item, { kind: "series" });
    expect(d.toast).toHaveBeenCalledWith(expect.objectContaining({ message: "Added to queue", href: "/queue" }));
  });

  it("toasts an error for blocked and failed saves", async () => {
    const b = deps({}, { result: "blocked" });
    await saveWebItem(b, item);
    expect(b.toast).toHaveBeenCalledWith({ kind: "error", message: "Blocked by a rule" });
    const e = deps({}, { result: "error" });
    await saveWebItem(e, item);
    expect(e.toast).toHaveBeenCalledWith({ kind: "error", message: "Could not save. Try again." });
  });
});

describe("save state", () => {
  it("uses the saved flag when the store has no entry", () => {
    const saved = { ...item, saved: { kind: "book", id: "b1" } } as WebItem;
    expect(saveStateFor(item, undefined)).toBe("idle");
    expect(saveStateFor(saved, undefined)).toBe("in_library");
    expect(saveStateFor(saved, { state: "queued" })).toBe("queued");
    expect(savedHrefFor(saved, undefined)).toBe("/item/books/b1");
    expect(savedHrefFor(item, undefined)).toBeUndefined();
  });
});

describe("settleQueued", () => {
  const job = (state: string, extra: Partial<Job> = {}) =>
    ({ source: "danbooru", post_id: "1", state, created_at: "2026-01-01", ...extra }) as Job;

  it("turns a done job into a tick with its library ref", () => {
    const ref = { kind: "image", id: "5" };
    expect(settleQueued(["danbooru:1"], [job("done", { library_ref: ref as Job["library_ref"] })])).toEqual({
      "danbooru:1": { state: "in_library", ref },
    });
  });

  it("sends a failed job back to idle and leaves a running job spinning", () => {
    expect(settleQueued(["danbooru:1"], [job("failed")])).toEqual({ "danbooru:1": "idle" });
    expect(settleQueued(["danbooru:1"], [job("running")])).toEqual({});
  });

  it("keeps a save spinning while Komga scans (scan_wait, verifying)", () => {
    expect(settleQueued(["danbooru:1"], [job("scan_wait")])).toEqual({});
    expect(settleQueued(["danbooru:1"], [job("verifying")])).toEqual({});
  });

  it("uses the newest job for the key", () => {
    const jobs = [job("failed", { created_at: "2026-01-01" }), job("running", { created_at: "2026-01-02" })];
    expect(settleQueued(["danbooru:1"], jobs)).toEqual({});
  });

  it("gives no link for a ref without an id", () => {
    const item = { saved: { kind: "book", id: "" } } as unknown as WebItem;
    expect(savedHrefFor(item, undefined)).toBeUndefined();
  });
});
