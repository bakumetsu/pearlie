import { describe, it, expect } from "vitest";
import { createGate, withPrio } from "./webImageQueue";

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("createGate", () => {
  it("lets 2 focus and 2 other requests in flight, no more", async () => {
    const g = createGate();
    const granted: string[] = [];
    (["focus", "focus", "focus", "cover", "prefetch", "prefetch"] as const).forEach((p, i) => {
      void g.acquire(p).ready.then(() => granted.push(p + i));
    });
    await tick();
    expect(granted).toEqual(["focus0", "focus1", "cover3", "prefetch4"]);
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

describe("withPrio", () => {
  it("adds the prio query", () => {
    expect(withPrio("/a/1", "focus")).toBe("/a/1?prio=focus");
    expect(withPrio("/a/1?x=1", "prefetch")).toBe("/a/1?x=1&prio=prefetch");
  });
});
