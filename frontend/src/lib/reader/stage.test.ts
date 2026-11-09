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
    onzoom: vi.fn(),
    onzoomstep: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("Stage dblclick zoom", () => {
  it("does not zoom on dblclick in prev zone", async () => {
    const props = makeProps();
    const { container } = render(Stage, props as never);
    mockStageRect();
    const stage = container.querySelector(".stage")!;
    await fireEvent.dblClick(stage, { clientX: 100, clientY: 400 });
    expect(props.onzoom).not.toHaveBeenCalled();
  });

  it("does not zoom on dblclick in next zone", async () => {
    const props = makeProps();
    const { container } = render(Stage, props as never);
    mockStageRect();
    const stage = container.querySelector(".stage")!;
    await fireEvent.dblClick(stage, { clientX: 900, clientY: 400 });
    expect(props.onzoom).not.toHaveBeenCalled();
  });

  it("zooms to 200 on dblclick in centre", async () => {
    const props = makeProps();
    const { container } = render(Stage, props as never);
    mockStageRect();
    const stage = container.querySelector(".stage")!;
    await fireEvent.dblClick(stage, { clientX: 500, clientY: 400 });
    expect(props.onzoom).toHaveBeenCalledTimes(1);
    expect(props.onzoom).toHaveBeenCalledWith(200);
  });

  it("zooms to 100 on dblclick in centre when already zoomed", async () => {
    const props = makeProps({ zoom: 200 });
    const { container } = render(Stage, props as never);
    mockStageRect();
    const stage = container.querySelector(".stage")!;
    await fireEvent.dblClick(stage, { clientX: 500, clientY: 400 });
    expect(props.onzoom).toHaveBeenCalledTimes(1);
    expect(props.onzoom).toHaveBeenCalledWith(100);
  });
});
