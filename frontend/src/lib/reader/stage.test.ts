import { render, fireEvent, cleanup } from "@testing-library/svelte";
import { describe, it, expect, vi, afterEach, beforeAll, afterAll } from "vitest";
import Stage from "./Stage.svelte";

beforeAll(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterAll(() => {
  vi.unstubAllGlobals();
});

const mockRect = {
  left: 0,
  width: 1000,
  top: 0,
  height: 800,
  right: 1000,
  bottom: 800,
  x: 0,
  y: 0,
  toJSON() {},
};

function mockStageRect() {
  const stage = document.querySelector(".stage")!;
  stage.getBoundingClientRect = () => mockRect;
}

function makeProps(overrides: Record<string, unknown> = {}) {
  return {
    shown: [1],
    groups: [[1]],
    page: 1,
    template: "/p/{n}",
    fit: "both",
    zoom: 100,
    dir: "ltr",
    est: null,
    onsize: vi.fn(),
    onturn: vi.fn(),
    ontoggle: vi.fn(),
    onzoomstep: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("Stage dblclick", () => {
  it("does not zoom on dblclick in any zone", async () => {
    const props = makeProps();
    const { container } = render(Stage, props as never);
    mockStageRect();
    const stage = container.querySelector(".stage")!;
    for (const x of [100, 500, 900]) {
      await fireEvent.dblClick(stage, { clientX: x, clientY: 400 });
    }
    expect(props.onzoomstep).not.toHaveBeenCalled();
    expect(props.onturn).not.toHaveBeenCalled();
  });
});

describe("Stage page slide", () => {
  it("first mount has no data-from", () => {
    const { container } = render(
      Stage,
      makeProps({ groups: [[1], [2], [3]], page: 1, shown: [1] }) as never,
    );
    const row = container.querySelector(".row")!;
    expect(row.getAttribute("data-from")).toBeNull();
  });

  it("ltr page 1→2: data-from is right", async () => {
    const props = makeProps({ groups: [[1], [2], [3]], page: 1, shown: [1] });
    const { container, rerender } = render(Stage, props as never);
    await rerender({ ...props, page: 2, shown: [2] } as never);
    const row = container.querySelector(".row")!;
    expect(row.getAttribute("data-from")).toBe("right");
  });

  it("ltr page 2→1: data-from is left", async () => {
    const props = makeProps({ groups: [[1], [2], [3]], page: 2, shown: [2] });
    const { container, rerender } = render(Stage, props as never);
    await rerender({ ...props, page: 1, shown: [1] } as never);
    const row = container.querySelector(".row")!;
    expect(row.getAttribute("data-from")).toBe("left");
  });

  it("rtl page 1→2: data-from is left", async () => {
    const props = makeProps({
      groups: [[1], [2], [3]],
      page: 1,
      shown: [1],
      dir: "rtl",
    });
    const { container, rerender } = render(Stage, props as never);
    await rerender({ ...props, page: 2, shown: [2] } as never);
    const row = container.querySelector(".row")!;
    expect(row.getAttribute("data-from")).toBe("left");
  });

  it("jump 1→3: no data-from", async () => {
    const props = makeProps({ groups: [[1], [2], [3]], page: 1, shown: [1] });
    const { container, rerender } = render(Stage, props as never);
    await rerender({ ...props, page: 3, shown: [3] } as never);
    const row = container.querySelector(".row")!;
    expect(row.getAttribute("data-from")).toBeNull();
  });

  it("reduced motion: no data-from on page change", async () => {
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      value: () => ({ matches: true }),
      writable: true,
      configurable: true,
    });
    try {
      const props = makeProps({ groups: [[1], [2], [3]], page: 1, shown: [1] });
      const { container, rerender } = render(Stage, props as never);
      await rerender({ ...props, page: 2, shown: [2] } as never);
      const row = container.querySelector(".row")!;
      expect(row.getAttribute("data-from")).toBeNull();
    } finally {
      Object.defineProperty(window, "matchMedia", {
        value: originalMatchMedia,
        writable: true,
        configurable: true,
      });
    }
  });
});
