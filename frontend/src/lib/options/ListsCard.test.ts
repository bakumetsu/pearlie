// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ListsCard from "./ListsCard.svelte";
import type { OptionsStore } from "../stores/options.svelte";

vi.mock("../stores/options.svelte", () => ({ options: { values: null, set: vi.fn() } }));

const store = (values: Record<string, unknown> | null) =>
  ({ values, set: vi.fn() }) as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };

afterEach(cleanup);

describe("ListsCard", () => {
  it("is off by default and turns on through the store", async () => {
    const s = store({});
    render(ListsCard, { store: s });
    const sw = screen.getByRole("switch", { name: "Infinite scroll" });
    expect(sw.getAttribute("aria-checked")).toBe("false");
    await fireEvent.click(sw);
    expect(s.set).toHaveBeenCalledWith({ infinite_scroll: true });
  });

  it("turns off when on", async () => {
    const s = store({ infinite_scroll: true });
    render(ListsCard, { store: s });
    const sw = screen.getByRole("switch", { name: "Infinite scroll" });
    expect(sw.getAttribute("aria-checked")).toBe("true");
    await fireEvent.click(sw);
    expect(s.set).toHaveBeenCalledWith({ infinite_scroll: false });
  });
});
