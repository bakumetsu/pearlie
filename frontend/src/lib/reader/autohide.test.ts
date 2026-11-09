import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createAutoHide } from "./autohide";

describe("createAutoHide", () => {
  let onchange: ReturnType<typeof vi.fn>;
  let blocked: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    onchange = vi.fn();
    blocked = vi.fn().mockReturnValue(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("hides after 4000 ms by default", () => {
    createAutoHide({ blocked, onchange });
    expect(onchange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(3999);
    expect(onchange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange).toHaveBeenCalledWith(true);
  });

  it("poke() shows again and restarts the timer", () => {
    const api = createAutoHide({ blocked, onchange });
    vi.advanceTimersByTime(4000);
    expect(onchange).toHaveBeenLastCalledWith(true);
    api.poke();
    expect(onchange).toHaveBeenCalledTimes(2);
    expect(onchange).toHaveBeenLastCalledWith(false);
    vi.advanceTimersByTime(3999);
    expect(onchange).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(1);
    expect(onchange).toHaveBeenCalledTimes(3);
    expect(onchange).toHaveBeenLastCalledWith(true);
  });

  it("stays visible while blocked() is true, hides after blocked turns false", () => {
    createAutoHide({ blocked, onchange });
    blocked.mockReturnValue(true);
    vi.advanceTimersByTime(4000);
    expect(onchange).not.toHaveBeenCalled();
    blocked.mockReturnValue(false);
    vi.advanceTimersByTime(4000);
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange).toHaveBeenCalledWith(true);
  });

  it("hover keeps it visible; hiding resumes after setHover(false) plus delay", () => {
    const api = createAutoHide({ blocked, onchange });
    vi.advanceTimersByTime(2000);
    api.setHover(true);
    vi.advanceTimersByTime(4000);
    expect(onchange).not.toHaveBeenCalled();
    api.setHover(false);
    vi.advanceTimersByTime(3999);
    expect(onchange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange).toHaveBeenCalledWith(true);
  });

  it("focus keeps it visible; hiding resumes after setFocus(false) plus delay", () => {
    const api = createAutoHide({ blocked, onchange });
    vi.advanceTimersByTime(2000);
    api.setFocus(true);
    vi.advanceTimersByTime(4000);
    expect(onchange).not.toHaveBeenCalled();
    api.setFocus(false);
    vi.advanceTimersByTime(4000);
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange).toHaveBeenCalledWith(true);
  });

  it("hide() does nothing while blocked", () => {
    const api = createAutoHide({ blocked, onchange });
    blocked.mockReturnValue(true);
    api.hide();
    expect(onchange).not.toHaveBeenCalled();
  });

  it("toggle() when hidden shows and restarts the timer", () => {
    const api = createAutoHide({ blocked, onchange });
    vi.advanceTimersByTime(4000);
    expect(onchange).toHaveBeenLastCalledWith(true);
    api.toggle();
    expect(onchange).toHaveBeenCalledTimes(2);
    expect(onchange).toHaveBeenLastCalledWith(false);
    vi.advanceTimersByTime(4000);
    expect(onchange).toHaveBeenCalledTimes(3);
    expect(onchange).toHaveBeenLastCalledWith(true);
  });

  it("destroy() cancels the timer", () => {
    const api = createAutoHide({ blocked, onchange });
    vi.advanceTimersByTime(2000);
    api.destroy();
    vi.advanceTimersByTime(10000);
    expect(onchange).not.toHaveBeenCalled();
  });

  it("respects custom delayMs", () => {
    createAutoHide({ blocked, onchange, delayMs: 1000 });
    vi.advanceTimersByTime(999);
    expect(onchange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange).toHaveBeenCalledWith(true);
  });
});
