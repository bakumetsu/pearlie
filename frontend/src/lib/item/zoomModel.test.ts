import { describe, it, expect, vi } from "vitest";
import { createZoom, wheelFactor, zoomKey } from "./zoomModel.svelte";

function make(sw: number, sh: number, nw: number, nh: number) {
  const z = createZoom();
  z.setSizes(sw, sh, nw, nh);
  return z;
}

function key(k: string, extra: Record<string, unknown> = {}) {
  return { key: k, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, preventDefault: vi.fn(), ...extra };
}

describe("zoomModel", () => {
  it("before setSizes: no NaN/Infinity after all ops; f is 1", () => {
    const z = createZoom();
    z.toggleAt(100, 200);
    z.zoomAt(2, 0, 0);
    z.stepIn();
    z.stepOut();
    z.panBy(10, 20);
    z.snap();
    expect(Number.isFinite(z.scale)).toBe(true);
    expect(Number.isFinite(z.tx)).toBe(true);
    expect(Number.isFinite(z.ty)).toBe(true);
    expect(Number.isFinite(z.f)).toBe(true);
    expect(Number.isFinite(z.percent)).toBe(true);
    expect(z.f).toBe(1);
  });

  it("anchor math: zoomAt keeps the picture point under the cursor fixed", () => {
    const z = make(1000, 600, 2000, 1200);
    const px = 200, py = 100;
    const q0 = { x: (px - z.tx) / z.scale, y: (py - z.ty) / z.scale };
    z.zoomAt(1, px, py);
    const q1 = { x: (px - z.tx) / z.scale, y: (py - z.ty) / z.scale };
    expect(q1.x).toBeCloseTo(q0.x);
    expect(q1.y).toBeCloseTo(q0.y);

    const px2 = 300, py2 = 200;
    const q2 = { x: (px2 - z.tx) / z.scale, y: (py2 - z.ty) / z.scale };
    z.zoomAt(2, px2, py2);
    const q3 = { x: (px2 - z.tx) / z.scale, y: (py2 - z.ty) / z.scale };
    expect(q3.x).toBeCloseTo(q2.x);
    expect(q3.y).toBeCloseTo(q2.y);
  });

  it("limits: clamps to min/max per fit scale", () => {
    const a = make(1600, 900, 8000, 4500);
    expect(a.min).toBeCloseTo(0.2);
    expect(a.max).toBe(2);
    a.zoomAt(0.1, 0, 0);
    expect(a.scale).toBeCloseTo(0.2);

    const b = make(1200, 800, 300, 200);
    expect(b.min).toBe(0.25);
    expect(b.max).toBe(4);
    b.zoomAt(5, 0, 0);
    expect(b.scale).toBe(4);

    const c = make(1000, 600, 2000, 1200);
    expect(c.min).toBe(0.25);
    expect(c.max).toBe(2);
    c.zoomAt(5, 0, 0);
    expect(c.scale).toBe(2);
  });

  it("ladder: stepIn/stepOut follow rungs", () => {
    const z = make(1000, 600, 2000, 1200);
    expect(z.stepIn()).toBe(true);
    expect(z.scale).toBeCloseTo(0.75);
    expect(z.stepIn()).toBe(true);
    expect(z.scale).toBeCloseTo(1);
    expect(z.stepIn()).toBe(true);
    expect(z.scale).toBeCloseTo(1.5);
    expect(z.stepIn()).toBe(true);
    expect(z.scale).toBeCloseTo(2);
    expect(z.stepIn()).toBe(false);

    const z2 = make(1000, 600, 2000, 1200);
    z2.stepIn();
    expect(z2.scale).toBeCloseTo(0.75);
    expect(z2.stepOut()).toBe(true);
    expect(z2.mode).toBe("fit");

    const z3 = make(1000, 600, 2000, 1200);
    z3.stepIn(); z3.stepIn(); z3.stepIn();
    expect(z3.scale).toBeCloseTo(1.5);
    expect(z3.stepOut()).toBe(true);
    expect(z3.scale).toBeCloseTo(1);

    const z4 = make(1000, 600, 2000, 1200);
    expect(z4.stepOut()).toBe(false);

    const z5 = make(1600, 900, 8000, 4500);
    expect(z5.stepIn()).toBe(true);
    expect(z5.scale).toBeCloseTo(0.25);
  });

  it("toggleAt: fit→zoom and zoom→fit; rung selection", () => {
    const z = make(1000, 600, 2000, 1200);
    expect(z.toggleAt(200, 100)).toBe(true);
    expect(z.scale).toBeCloseTo(1);
    expect(z.toggleAt(200, 100)).toBe(true);
    expect(z.mode).toBe("fit");

    const z2 = make(960, 960, 1000, 1000);
    expect(z2.toggleAt(0, 0)).toBe(true);
    expect(z2.scale).toBeCloseTo(1);

    const z3 = make(1200, 1200, 1000, 1000);
    expect(z3.toggleAt(0, 0)).toBe(true);
    expect(z3.scale).toBeCloseTo(1.5);

    const z4 = make(1200, 800, 300, 200);
    expect(z4.toggleAt(0, 0)).toBe(false);
    expect(z4.mode).toBe("fit");
  });

  it("snap: near-fit resets, near-1 snaps, else unchanged", () => {
    const z = make(1000, 600, 2000, 1200);
    z.zoomAt(0.51, 0, 0);
    z.snap();
    expect(z.mode).toBe("fit");

    const z2 = make(1000, 600, 2000, 1200);
    z2.zoomAt(1.03, 0, 0);
    z2.snap();
    expect(z2.scale).toBe(1);

    const z3 = make(1000, 600, 2000, 1200);
    z3.zoomAt(1.2, 0, 0);
    z3.snap();
    expect(z3.scale).toBeCloseTo(1.2);
  });
});

describe("zoomModel pan, resize, keys", () => {
  it("pan clamp: positive, negative, sub-fit, and at fit", () => {
    const z = make(1000, 600, 2000, 1200);
    z.zoomAt(2, 0, 0);
    z.panBy(5000, 5000);
    expect(z.tx).toBe(1500);
    expect(z.ty).toBe(900);

    const z2 = make(1000, 600, 2000, 1200);
    z2.zoomAt(2, 0, 0);
    z2.panBy(-5000, -5000);
    expect(z2.tx).toBe(-1500);
    expect(z2.ty).toBe(-900);

    const z3 = make(1000, 600, 2000, 1200);
    z3.zoomAt(0.25, 0, 0);
    z3.panBy(100, 100);
    expect(z3.tx).toBe(0);
    expect(z3.ty).toBe(0);

    const z4 = make(1000, 600, 2000, 1200);
    z4.panBy(100, 100);
    expect(z4.tx).toBe(0);
    expect(z4.ty).toBe(0);
  });

  it("setSizes re-clamps pan and snaps to fit when scale ≈ f", () => {
    const z = make(1000, 600, 2000, 1200);
    z.zoomAt(2, 0, 0);
    z.panBy(10000, 10000);
    z.setSizes(2000, 1200, 2000, 1200);
    expect(z.mode).toBe("zoom");
    expect(z.tx).toBe(1000);
    expect(z.ty).toBe(600);

    const z2 = make(1000, 600, 2000, 1200);
    z2.zoomAt(0.5, 0, 0);
    z2.setSizes(1000, 600, 2000, 1200);
    expect(z2.mode).toBe("fit");
    expect(z2.tx).toBe(0);
    expect(z2.ty).toBe(0);
  });

  it("reset/fit return fit mode and zero pan; percent = round(scale*100)", () => {
    const z = make(1000, 600, 2000, 1200);
    z.zoomAt(2, 0, 0);
    z.panBy(100, 200);
    z.reset();
    expect(z.mode).toBe("fit");
    expect(z.tx).toBe(0);
    expect(z.ty).toBe(0);

    const z2 = make(1000, 600, 2000, 1200);
    z2.zoomAt(2, 0, 0);
    z2.fit();
    expect(z2.mode).toBe("fit");
    expect(z2.tx).toBe(0);
    expect(z2.ty).toBe(0);

    const z3 = make(1000, 600, 2000, 1200);
    z3.zoomAt(1.5, 0, 0);
    expect(z3.percent).toBe(150);
  });

  it("wheelFactor: pixel, line, and ctrl modes", () => {
    expect(wheelFactor(-100, 0, false)).toBeCloseTo(Math.exp(0.2));
    expect(wheelFactor(100, 1, false)).toBeCloseTo(Math.exp(-0.002 * 1600));
    expect(wheelFactor(-100, 0, true)).toBeCloseTo(Math.exp(1));
  });

  it("zoomKey: all key bindings", () => {
    const z1 = make(1000, 600, 2000, 1200);
    const e1 = key("+");
    expect(zoomKey(e1, z1)).toBe(true);
    expect(e1.preventDefault).toHaveBeenCalled();

    const z1b = make(1000, 600, 2000, 1200);
    const e1b = key("=", { shiftKey: true });
    expect(zoomKey(e1b, z1b)).toBe(true);
    expect(e1b.preventDefault).toHaveBeenCalled();

    const z2 = make(1000, 600, 2000, 1200);
    z2.zoomAt(1.5, 0, 0);
    const e2 = key("-");
    expect(zoomKey(e2, z2)).toBe(true);
    expect(z2.scale).toBeCloseTo(1);

    const z3 = make(1000, 600, 2000, 1200);
    const e3 = key("-");
    expect(zoomKey(e3, z3)).toBe(false);
    expect(e3.preventDefault).not.toHaveBeenCalled();

    const z4 = make(1000, 600, 2000, 1200);
    z4.zoomAt(2, 0, 0);
    const e4 = key("0");
    expect(zoomKey(e4, z4)).toBe(true);
    expect(z4.mode).toBe("fit");
    expect(e4.preventDefault).toHaveBeenCalled();

    const z5 = make(1000, 600, 2000, 1200);
    const e5 = key("0");
    expect(zoomKey(e5, z5)).toBe(false);

    const z6 = make(1000, 600, 2000, 1200);
    const e6 = key("z");
    expect(zoomKey(e6, z6)).toBe(true);
    expect(z6.mode).toBe("zoom");
    const e6b = key("Z");
    expect(zoomKey(e6b, z6)).toBe(true);
    expect(z6.mode).toBe("fit");

    const z7 = make(1000, 600, 2000, 1200);
    z7.zoomAt(2, 0, 0);
    const e7 = key("Escape");
    expect(zoomKey(e7, z7)).toBe(true);
    expect(z7.mode).toBe("fit");
    expect(e7.preventDefault).toHaveBeenCalled();

    const z8 = make(1000, 600, 2000, 1200);
    const e8 = key("Escape");
    expect(zoomKey(e8, z8)).toBe(false);

    const z9 = make(1000, 600, 2000, 1200);
    z9.zoomAt(2, 0, 0);
    const e9 = key("ArrowRight", { shiftKey: true });
    expect(zoomKey(e9, z9)).toBe(true);
    expect(z9.tx).toBe(-80);
    zoomKey(key("ArrowLeft", { shiftKey: true }), z9);
    expect(z9.tx).toBe(0);
    zoomKey(key("ArrowUp", { shiftKey: true }), z9);
    expect(z9.ty).toBe(80);
    zoomKey(key("ArrowDown", { shiftKey: true }), z9);
    expect(z9.ty).toBe(0);

    const z10 = make(1000, 600, 2000, 1200);
    const e10 = key("ArrowRight", { shiftKey: true });
    expect(zoomKey(e10, z10)).toBe(false);
    expect(z10.tx).toBe(0);

    const z11 = make(1000, 600, 2000, 1200);
    z11.zoomAt(2, 0, 0);
    const e11 = key("ArrowLeft");
    expect(zoomKey(e11, z11)).toBe(false);

    const z12 = make(1000, 600, 2000, 1200);
    const s12 = z12.scale;
    expect(zoomKey(key("+", { ctrlKey: true }), z12)).toBe(false);
    expect(zoomKey(key("+", { metaKey: true }), z12)).toBe(false);
    expect(zoomKey(key("+", { altKey: true }), z12)).toBe(false);
    expect(z12.scale).toBe(s12);

    const z13 = make(1000, 600, 2000, 1200);
    expect(zoomKey(key("q"), z13)).toBe(false);
  });
});
