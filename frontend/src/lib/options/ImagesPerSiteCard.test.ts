// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ImagesPerSiteCard from "./ImagesPerSiteCard.svelte";
import type { OptionsStore } from "../stores/options.svelte";

type Entry = { value: number; default: number; locked: boolean; backing_off: boolean };

function pace(over: Record<string, Partial<Entry>> = {}) {
  const base = (v: number): Entry => ({ value: v, default: v, locked: false, backing_off: false });
  return {
    danbooru: { ...base(1), ...over.danbooru },
    gelbooru: { ...base(1), ...over.gelbooru },
    rule34: { ...base(1), ...over.rule34 },
    nhentai: { ...base(2), ...over.nhentai },
  };
}

function makeStore(values: Record<string, unknown> | null) {
  return { values, set: vi.fn() } as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };
}

afterEach(cleanup);

describe("ImagesPerSiteCard delay lines", () => {
  it("shows one delay line per site with the default as tooltip", () => {
    render(ImagesPerSiteCard, { store: makeStore({ source_pace: pace() }) });
    expect(screen.getByText("Delay between requests")).toBeDefined();
    expect((screen.getByTestId("pace-nhentai") as HTMLInputElement).value).toBe("2");
    expect(screen.getByTestId("pace-danbooru").getAttribute("title")).toBe("Seconds between requests. Default 1s");
  });

  it("a valid change calls store.set with the new pace", () => {
    const store = makeStore({ source_pace: pace() });
    render(ImagesPerSiteCard, { store });
    fireEvent.change(screen.getByTestId("pace-danbooru"), { target: { value: "3" } });
    expect(store.set).toHaveBeenCalledWith({ source_pace: { danbooru: 3 } });
  });

  it("below the default shows the minimum and does not save", async () => {
    const store = makeStore({ source_pace: pace() });
    render(ImagesPerSiteCard, { store });
    fireEvent.change(screen.getByTestId("pace-nhentai"), { target: { value: "1" } });
    expect(store.set).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toBe("Minimum is 2s");
  });

  it("a locked site is disabled with a .env chip", () => {
    render(ImagesPerSiteCard, { store: makeStore({ source_pace: pace({ rule34: { locked: true } }) }) });
    expect((screen.getByTestId("pace-rule34") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("set in .env")).toBeDefined();
  });

  it("images at a time still saves", () => {
    const store = makeStore({ images_per_site: 10, source_pace: pace() });
    render(ImagesPerSiteCard, { store });
    fireEvent.change(screen.getByTestId("images-per-site"), { target: { value: "8" } });
    expect(store.set).toHaveBeenCalledWith({ images_per_site: 8 });
  });
});
