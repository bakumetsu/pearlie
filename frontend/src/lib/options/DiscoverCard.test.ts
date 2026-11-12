// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import DiscoverCard from "./DiscoverCard.svelte";
import type { OptionsStore } from "../stores/options.svelte";

vi.mock("../stores/toasts.svelte", () => ({ toasts: { push: vi.fn() } }));

function makeStore(values: Record<string, unknown> | null) {
  return { values, set: vi.fn() } as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };
}

afterEach(cleanup);

describe("DiscoverCard", () => {
  it("shows every site on by default", () => {
    render(DiscoverCard, { store: makeStore({ hidden_sites: [] }) });
    for (const n of ["Danbooru", "Gelbooru", "Rule34", "nhentai"]) {
      expect(screen.getByRole("switch", { name: `Show ${n} in rail` }).getAttribute("aria-checked")).toBe("true");
    }
  });

  it("hides a site by saving it in hidden_sites", async () => {
    const store = makeStore({ hidden_sites: ["rule34"] });
    render(DiscoverCard, { store });
    expect(screen.getByRole("switch", { name: "Show Rule34 in rail" }).getAttribute("aria-checked")).toBe("false");
    await fireEvent.click(screen.getByRole("switch", { name: "Show Gelbooru in rail" }));
    expect(store.set).toHaveBeenCalledWith({ hidden_sites: ["rule34", "gelbooru"] });
  });

  it("shows a hidden site again", async () => {
    const store = makeStore({ hidden_sites: ["rule34", "nhentai"] });
    render(DiscoverCard, { store });
    await fireEvent.click(screen.getByRole("switch", { name: "Show Rule34 in rail" }));
    expect(store.set).toHaveBeenCalledWith({ hidden_sites: ["nhentai"] });
  });

  it("disables the switch of the last visible site", async () => {
    const store = makeStore({ hidden_sites: ["gelbooru", "rule34", "nhentai"] });
    render(DiscoverCard, { store });
    const sw = screen.getByRole("switch", { name: "Show Danbooru in rail" }) as HTMLButtonElement;
    expect(sw.disabled).toBe(true);
    expect(screen.getByText("At least one site stays on.")).toBeTruthy();
    await fireEvent.click(sw);
    expect(store.set).not.toHaveBeenCalled();
    expect((screen.getByRole("switch", { name: "Show Rule34 in rail" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
