// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import DownloadsCard from "./DownloadsCard.svelte";
import type { OptionsStore } from "../stores/options.svelte";

vi.mock("../stores/options.svelte", () => ({
  options: { values: null, set: vi.fn() },
}));

type PaceEntry = { value: number; default: number; locked: boolean; backing_off: boolean };
type PaceMap = Record<"danbooru" | "nhentai" | "gelbooru" | "rule34", PaceEntry>;

function pace(over: Partial<Record<string, Partial<PaceEntry>>> = {}): PaceMap {
  return {
    danbooru: { value: 1, default: 1, locked: false, backing_off: false, ...over.danbooru },
    nhentai: { value: 2, default: 2, locked: false, backing_off: false, ...over.nhentai },
    gelbooru: { value: 1, default: 1, locked: false, backing_off: false, ...over.gelbooru },
    rule34: { value: 1, default: 1, locked: false, backing_off: false, ...over.rule34 },
  };
}

function makeStore(values: Record<string, unknown> | null) {
  return { values, set: vi.fn() } as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("DownloadsCard", () => {
  it("store.values null shows four rows with defaults", () => {
    const store = makeStore(null);
    render(DownloadsCard, { store });

    const danbooru = screen.getByTestId("pace-danbooru") as HTMLInputElement;
    expect(danbooru.value).toBe("1");

    const nhentai = screen.getByTestId("pace-nhentai") as HTMLInputElement;
    expect(nhentai.value).toBe("2");

    expect(screen.getByText("default 1s")).toBeDefined();
  });

  it("valid change calls store.set with the new pace", () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    const input = screen.getByTestId("pace-danbooru");
    fireEvent.change(input, { target: { value: "3" } });

    expect(store.set).toHaveBeenCalledWith({ source_pace: { danbooru: 3 } });
  });

  it("below default does not call set and shows minimum alert", () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    const input = screen.getByTestId("pace-nhentai");
    fireEvent.change(input, { target: { value: "1" } });

    expect(store.set).not.toHaveBeenCalled();
    expect(screen.getByRole("alert", { name: "Minimum is 2s" })).toBeDefined();
  });

  it("backing_off true shows exactly one status element", () => {
    const store = makeStore({ source_pace: pace({ gelbooru: { backing_off: true } }) });
    render(DownloadsCard, { store });

    expect(screen.getAllByRole("status", { name: "Backing off" })).toHaveLength(1);
  });

  it("locked true disables input and shows env text", () => {
    const store = makeStore({ source_pace: pace({ rule34: { locked: true } }) });
    render(DownloadsCard, { store });

    const input = screen.getByTestId("pace-rule34") as HTMLInputElement;
    expect(input.disabled).toBe(true);
    expect(screen.getByText("set in .env")).toBeDefined();
  });
});
