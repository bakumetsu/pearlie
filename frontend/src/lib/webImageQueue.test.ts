import { describe, it, expect, vi } from "vitest";
import { createGate, withPrio, gatedSrc, GATE_HOLD_MS } from "./webImageQueue";

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("createGate", () => {
  it("lets 2 focus and 2 other requests in flight, no more", async () => {
    const g = createGate();
    const granted: string[] = [];
    (["focus", "focus", "cover", "cover", "prefetch"] as const).forEach((p, i) => {
      void g.acquire(p).ready.then(() => granted.push(p + i));
    });
    await tick();
    expect(granted).toEqual(["focus0", "focus1", "cover2", "cover3"]);
  });

  it("starts the next waiting request when one is released", async () => {
    const g = createGate();
    const rel: Array<() => void> = [];
    const order: number[] = [];
    for (let i = 0; i < 4; i++) {
      void g.acquire("prefetch").ready.then((r) => {
        rel.push(r);
        order.push(i);
      });
    }
    await tick();
    expect(order).toEqual([0, 1]);
    rel[0]();
    rel[0]();
    await tick();
    expect(order).toEqual([0, 1, 2]);
  });

  it("serves cover before prefetch and skips cancelled jobs", async () => {
    const g = createGate({ focus: 1, other: 1 });
    const order: string[] = [];
    let first!: () => void;
    void g.acquire("prefetch").ready.then((r) => (first = r));
    await tick();
    void g.acquire("prefetch").ready.then(() => order.push("prefetch"));
    void g.acquire("cover").ready.then(() => order.push("cover"));
    const gone = g.acquire("cover");
    void gone.ready.then(() => order.push("gone"));
    gone.cancel();
    first();
    await tick();
    expect(order).toEqual(["cover"]);
  });
});

describe("focus borrowing", () => {
  it("lets focus take idle other slots, but other never takes focus slots", async () => {
    const g = createGate();
    const got: string[] = [];
    (["focus", "focus", "focus", "focus", "focus"] as const).forEach((p, i) => void g.acquire(p).ready.then(() => got.push(p + i)));
    await tick();
    expect(got).toEqual(["focus0", "focus1", "focus2", "focus3"]);
    const g2 = createGate();
    const got2: string[] = [];
    (["prefetch", "prefetch", "prefetch"] as const).forEach((p, i) => void g2.acquire(p).ready.then(() => got2.push(p + i)));
    await tick();
    expect(got2).toEqual(["prefetch0", "prefetch1"]);
  });
});

describe("withPrio", () => {
  it("adds the prio query", () => {
    expect(withPrio("/a/1", "focus")).toBe("/a/1");
    expect(withPrio("/a/1?x=1", "prefetch")).toBe("/a/1?x=1&prio=prefetch");
  });
});

describe("gatedSrc timeout", () => {
  it("frees the slot when the image neither loads nor errors", async () => {
    vi.useFakeTimers();
    try {
      const g = createGate({ focus: 1, other: 1 });
      const node = { src: "", removeAttribute() {}, addEventListener() {}, removeEventListener() {} };
      gatedSrc(node as unknown as HTMLImageElement, { src: "/a/1", prio: "cover", gate: g });
      let second = false;
      void g.acquire("cover").ready.then(() => (second = true));
      await vi.advanceTimersByTimeAsync(GATE_HOLD_MS - 1);
      expect(second).toBe(false);
      await vi.advanceTimersByTimeAsync(2);
      expect(second).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
