import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createToasts } from "./toasts.svelte";

describe("createToasts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("makes the first push current immediately", () => {
    const t = createToasts();
    const id = t.push({ kind: "info", message: "hello" });
    expect(t.current?.id).toBe(id);
    expect(t.current?.message).toBe("hello");
    expect(t.queued).toBe(0);
  });

  it("queues the second push without changing current", () => {
    const t = createToasts();
    const id1 = t.push({ kind: "info", message: "first" });
    t.push({ kind: "info", message: "second" });
    expect(t.queued).toBe(1);
    expect(t.current?.id).toBe(id1);
  });

  it("auto-dismisses info after 4000 ms and promotes the queued toast", () => {
    const t = createToasts();
    t.push({ kind: "info", message: "first" });
    const id2 = t.push({ kind: "info", message: "second" });
    vi.advanceTimersByTime(4000);
    expect(t.current?.id).toBe(id2);
  });

  it("keeps an undo toast for 10000 ms", () => {
    const t = createToasts();
    const id = t.push({ kind: "undo", message: "undo" });
    vi.advanceTimersByTime(9999);
    expect(t.current?.id).toBe(id);
    vi.advanceTimersByTime(1);
    expect(t.current).toBeNull();
  });

  it("pauses at 4000 ms, survives 20 s, resumes and expires after remaining 6000 ms", () => {
    const t = createToasts();
    t.push({ kind: "undo", message: "undo" });
    vi.advanceTimersByTime(4000);
    t.pause();
    vi.advanceTimersByTime(20000);
    expect(t.current?.message).toBe("undo");
    t.resume();
    vi.advanceTimersByTime(6000);
    expect(t.current).toBeNull();
  });

  it("dismiss() promotes the next queued toast", () => {
    const t = createToasts();
    const id1 = t.push({ kind: "info", message: "first" });
    const id2 = t.push({ kind: "info", message: "second" });
    t.dismiss();
    expect(t.current?.id).toBe(id2);
    expect(t.current?.id).not.toBe(id1);
  });

  it("dismiss(id) removes only that queued toast", () => {
    const t = createToasts();
    const id1 = t.push({ kind: "info", message: "first" });
    const id2 = t.push({ kind: "info", message: "second" });
    t.push({ kind: "info", message: "third" });
    t.dismiss(id2);
    expect(t.queued).toBe(1);
    expect(t.current?.id).toBe(id1);
  });

  it("runAction calls onAction once and dismisses", () => {
    const spy = vi.fn();
    const t = createToasts();
    t.push({ kind: "undo", message: "undo", onAction: spy });
    t.runAction();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(t.current).toBeNull();
  });
  describe("visible", () => {
    it("is empty when nothing is shown", () => {
      expect(createToasts().visible).toEqual([]);
    });

    it("lists current then queue, capped at 3", () => {
      const t = createToasts();
      for (const m of ["a", "b", "c", "d"]) t.push({ kind: "info", message: m });
      expect(t.visible.map((x) => x.message)).toEqual(["a", "b", "c"]);
    });

    it("puts Undo toasts first without changing current or queued", () => {
      const t = createToasts();
      t.push({ kind: "info", message: "a" });
      t.push({ kind: "error", message: "b" });
      t.push({ kind: "undo", message: "u", actionLabel: "Undo" });
      expect(t.visible.map((x) => x.message)).toEqual(["u", "a", "b"]);
      expect(t.current?.message).toBe("a");
      expect(t.queued).toBe(2);
    });
  });
});
