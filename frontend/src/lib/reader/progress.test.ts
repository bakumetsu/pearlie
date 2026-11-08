import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createProgress } from "./progress";

describe("createProgress", () => {
  let save: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    save = vi.fn().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("set saves once after 800 ms", () => {
    const api = createProgress(save);
    api.set("book1", 42);
    expect(save).not.toHaveBeenCalled();
    vi.advanceTimersByTime(799);
    expect(save).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("book1", 42, undefined);
  });

  it("only the last page of rapid sets is saved", () => {
    const api = createProgress(save);
    api.set("book1", 1);
    vi.advanceTimersByTime(100);
    api.set("book1", 2);
    vi.advanceTimersByTime(100);
    api.set("book1", 3);
    vi.advanceTimersByTime(800);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("book1", 3, undefined);
  });

  it("flush() saves immediately", () => {
    const api = createProgress(save);
    api.set("book1", 10);
    api.flush();
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("book1", 10, undefined);
  });

  it("flush(true) passes {keepalive:true}", () => {
    const api = createProgress(save);
    api.set("book1", 10);
    api.flush(true);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("book1", 10, { keepalive: true });
  });

  it("setting another bookId flushes the previous book first", () => {
    const api = createProgress(save);
    api.set("bookA", 5);
    api.set("bookB", 9);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("bookA", 5, undefined);
    vi.advanceTimersByTime(800);
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenCalledWith("bookB", 9, undefined);
  });

  it("cancel() drops the pending save", () => {
    const api = createProgress(save);
    api.set("book1", 7);
    api.cancel();
    vi.advanceTimersByTime(2000);
    expect(save).not.toHaveBeenCalled();
  });

  it("save rejection is swallowed", () => {
    save.mockRejectedValue(new Error("db error"));
    const api = createProgress(save);
    api.set("book1", 1);
    vi.advanceTimersByTime(800);
    expect(save).toHaveBeenCalledTimes(1);
    // no unhandled rejection thrown
  });

  it("sync throw in save is swallowed", () => {
    save.mockImplementation(() => { throw new Error("sync fail"); });
    const api = createProgress(save);
    expect(() => {
      api.set("book1", 1);
      vi.advanceTimersByTime(800);
    }).not.toThrow();
    expect(save).toHaveBeenCalledTimes(1);
  });
});
