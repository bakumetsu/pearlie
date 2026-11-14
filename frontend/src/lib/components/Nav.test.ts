// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import Nav from "./Nav.svelte";

describe("Nav rail", () => {
  afterEach(() => {
    cleanup();
    delete document.documentElement.dataset.rail;
  });

  it("hides with the toggle and shows the reopen chevron", async () => {
    render(Nav, { current: "home", onnavigate: () => {} });
    expect(screen.queryByRole("button", { name: "Show navigation" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Hide navigation" }));
    expect(document.documentElement.dataset.rail).toBe("hidden");
    const reopen = screen.getByRole("button", { name: "Show navigation" });
    await fireEvent.click(reopen);
    expect(document.documentElement.dataset.rail).toBeUndefined();
  });
});
