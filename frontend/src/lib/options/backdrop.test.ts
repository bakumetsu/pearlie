import { describe, it, expect } from "vitest";
import { render } from "@testing-library/svelte";
import { backdropStrength } from "./backdrop";
import Backdrop from "../components/Backdrop.svelte";

describe("backdropStrength", () => {
  it("returns 60 when values is null", () => {
    expect(backdropStrength(null, "wall")).toBe(60);
  });

  it("returns 0 when the switch for `where` is off", () => {
    expect(
      backdropStrength({ backdrop_strength: 60, backdrop_wall: false, backdrop_item: true, backdrop_lightbox: true }, "wall"),
    ).toBe(0);
  });

  it("returns 0 when strength is 0", () => {
    expect(
      backdropStrength({ backdrop_strength: 0, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true }, "wall"),
    ).toBe(0);
  });

  it("clamps 150 to 100", () => {
    expect(
      backdropStrength({ backdrop_strength: 150, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true }, "wall"),
    ).toBe(100);
  });

  it("clamps -5 to 0", () => {
    expect(
      backdropStrength({ backdrop_strength: -5, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true }, "wall"),
    ).toBe(0);
  });

  it("returns default 60 for NaN strength", () => {
    expect(
      backdropStrength({ backdrop_strength: NaN, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true }, "wall"),
    ).toBe(60);
  });
});

describe("Backdrop.svelte", () => {
  it("renders nothing at strength 0", () => {
    const { queryByTestId } = render(Backdrop, { props: { src: "test.jpg", strength: 0 } });
    expect(queryByTestId("backdrop")).toBeNull();
  });

  it("renders nothing when no src", () => {
    const { queryByTestId } = render(Backdrop, { props: { src: null, strength: 60 } });
    expect(queryByTestId("backdrop")).toBeNull();
  });

  it("sets opacity 0.4 at strength 40", () => {
    const { getByTestId } = render(Backdrop, { props: { src: "test.jpg", strength: 40 } });
    const fill = getByTestId("backdrop").querySelector(".fill") as HTMLElement;
    expect(fill).not.toBeNull();
    expect(fill.style.opacity).toBe("0.4");
  });
});

describe("backdropStrength in safe mode", () => {
  const on = { backdrop_strength: 60, backdrop_wall: true, backdrop_item: true, backdrop_lightbox: true };

  it("returns 0 while safe mode hides the backdrop", () => {
    expect(backdropStrength(on, "wall", true)).toBe(0);
    expect(backdropStrength(null, "item", true)).toBe(0);
  });

  it("keeps the strength when safe mode is off", () => {
    expect(backdropStrength(on, "lightbox", false)).toBe(60);
  });
});
