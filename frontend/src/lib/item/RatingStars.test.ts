import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import RatingStars from "./RatingStars.svelte";

describe("RatingStars", () => {
  afterEach(cleanup);

  it("marks the current value checked", () => {
    render(RatingStars, { value: 3, onrate: vi.fn() });
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(5);
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["false", "false", "true", "false", "false"]);
  });

  it("reports the tapped star, including the current one", async () => {
    const onrate = vi.fn();
    render(RatingStars, { value: 3, onrate });
    await fireEvent.click(screen.getByLabelText("Rating 4 of 5"));
    await fireEvent.click(screen.getByLabelText("Rating 3 of 5"));
    expect(onrate.mock.calls).toEqual([[4], [3]]);
  });

  it("has no checked star when unrated", () => {
    render(RatingStars, { value: null, onrate: vi.fn() });
    expect(screen.getAllByRole("radio").every((r) => r.getAttribute("aria-checked") === "false")).toBe(true);
  });
});
