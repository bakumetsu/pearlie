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

    expect(screen.getAllByText("default 1s")).toHaveLength(3);
  });

  it("valid change calls store.set with the new pace", () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    const input = screen.getByTestId("pace-danbooru");
    fireEvent.change(input, { target: { value: "3" } });

    expect(store.set).toHaveBeenCalledWith({ source_pace: { danbooru: 3 } });
  });

  it("below default does not call set and shows minimum alert", async () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    const input = screen.getByTestId("pace-nhentai");
    fireEvent.change(input, { target: { value: "1" } });

    expect(store.set).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toBe("Minimum is 2s");
  });

  it("backing_off true shows exactly one status element", () => {
    const store = makeStore({ source_pace: pace({ gelbooru: { backing_off: true } }) });
    render(DownloadsCard, { store });

    const status = screen.getAllByRole("status");
    expect(status).toHaveLength(1);
    expect(status[0].textContent).toBe("Backing off");
  });

  it("locked true disables input and shows env text", () => {
    const store = makeStore({ source_pace: pace({ rule34: { locked: true } }) });
    render(DownloadsCard, { store });

    const input = screen.getByTestId("pace-rule34") as HTMLInputElement;
    expect(input.disabled).toBe(true);
    expect(screen.getByText("set in .env")).toBeDefined();
  });

  it("above 3600 does not call set and shows maximum alert", async () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    fireEvent.change(screen.getByTestId("pace-danbooru"), { target: { value: "3601" } });

    expect(store.set).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toBe("Maximum is 3600s");
  });

  it("a rejected PUT restores the server value in the input", async () => {
    const actual = await vi.importActual<typeof import("../stores/options.svelte")>(
      "../stores/options.svelte",
    );
    const server = { sfw: false, player_rate: 1, source_pace: pace() };
    const api = {
      getOptions: vi.fn().mockResolvedValue(server),
      putOptions: vi.fn().mockRejectedValue(new Error("422")),
    };
    const real = actual.createOptions({
      sfw: { set: () => {} },
      player: { loadRate: () => {} },
      debounceMs: 0,
    });
    await real.load(api as never);
    render(DownloadsCard, { store: real });

    const input = screen.getByTestId("pace-danbooru") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "5" } });

    await vi.waitFor(() => expect(api.putOptions).toHaveBeenCalled());
    await vi.waitFor(() => expect(input.value).toBe("1"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("plus button steps the pace and saves it", () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    fireEvent.click(screen.getByRole("button", { name: "Increase Danbooru seconds" }));

    expect(store.set).toHaveBeenCalledWith({ source_pace: { danbooru: 1.5 } });
  });

  it("minus button at the minimum saves nothing", () => {
    const store = makeStore({ source_pace: pace() });
    render(DownloadsCard, { store });

    fireEvent.click(screen.getByRole("button", { name: "Decrease Danbooru seconds" }));

    expect(store.set).not.toHaveBeenCalled();
  });

  it("locked site disables its step buttons", () => {
    const store = makeStore({ source_pace: pace({ rule34: { locked: true } }) });
    render(DownloadsCard, { store });

    expect(
      (screen.getByRole("button", { name: "Increase Rule34 seconds" }) as HTMLButtonElement).disabled
    ).toBe(true);
  });
});
