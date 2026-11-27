// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/svelte";
import SitesCard from "./SitesCard.svelte";
import { createConnections } from "../stores/connections.svelte";
import type { OptionsStore } from "../stores/options.svelte";
import type { Api, ConnectionsOut, ConnectionOut, ConnectionTest } from "../api/client";

function conn(name: string, over: Partial<ConnectionOut> = {}): ConnectionOut {
  return {
    name,
    address: `https://${name}.example`,
    key: "missing",
    address_fixed: true,
    address_locked: true,
    key_locked: false,
    fields: [],
    ...over,
  } as ConnectionOut;
}

function makeApi(list: ConnectionOut[], test: ConnectionTest = { ok: true, message: "ok" }) {
  const data: ConnectionsOut = { can_store: true, connections: list };
  const getConnections = vi.fn().mockResolvedValue(data);
  const testConnection = vi.fn().mockResolvedValue(test);
  const api = { getConnections, testConnection, putConnection: vi.fn() } as unknown as Api;
  return { api, testConnection };
}

function optionsStore(pace: Record<string, { backing_off: boolean }> = {}) {
  return { values: { source_pace: pace }, set: vi.fn() } as unknown as OptionsStore;
}

async function renderCard(list: ConnectionOut[], pace = {}, test?: ConnectionTest) {
  const { api, testConnection } = makeApi(list, test);
  const store = createConnections();
  render(SitesCard, { store, optionsStore: optionsStore(pace), api });
  await vi.waitFor(() => expect(store.data).not.toBeNull());
  return { testConnection };
}

function row(key: string) {
  return within(screen.getByTestId(`site-${key}`));
}

const ALL = () => [conn("danbooru", { key: "set" }), conn("gelbooru"), conn("rule34"), conn("nhentai")];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("SitesCard", () => {
  it("shows one row per site with pill, URL, Test and settings buttons", async () => {
    await renderCard(ALL());
    expect(screen.getAllByTestId(/^site-/)).toHaveLength(4);
    expect(row("danbooru").getByText("Ready")).toBeDefined();
    expect(row("gelbooru").getByText("No key")).toBeDefined();
    expect(row("danbooru").getByText("https://danbooru.example")).toBeDefined();
    expect(row("danbooru").getByRole("button", { name: "Test Danbooru" })).toBeDefined();
    expect(row("danbooru").getByRole("button", { name: "Edit Danbooru" })).toBeDefined();
  });

  it("nhentai with a rejected key shows Key rejected, a reason line and an Edit key link", async () => {
    await renderCard([conn("nhentai", { key: "set", auth: "failed", reason: "invalid" })]);
    expect(row("nhentai").getByText("Key rejected")).toBeDefined();
    expect(row("nhentai").getByText(/nhentai rejected this key/)).toBeDefined();
    expect(row("nhentai").getByRole("button", { name: "Edit key" })).toBeDefined();
  });

  it("backing_off from the options store shows Backing off", async () => {
    await renderCard([conn("rule34", { key: "set" })], { rule34: { backing_off: true } });
    expect(row("rule34").getByText("Backing off")).toBeDefined();
    expect(row("rule34").getByText(/The site said slow down/)).toBeDefined();
  });

  it("a failed Test shows Down with the API message", async () => {
    await renderCard([conn("gelbooru", { key: "set" })], {}, { ok: false, message: "Test failed: timeout" });
    await fireEvent.click(row("gelbooru").getByRole("button", { name: "Test Gelbooru" }));
    await vi.waitFor(() => expect(row("gelbooru").getByText("Down")).toBeDefined());
    expect(row("gelbooru").getByText(/Test failed: timeout/)).toBeDefined();
  });

  it("a good Test shows Ready and Connected for 4 s", async () => {
    const { testConnection } = await renderCard([conn("gelbooru")]);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await fireEvent.click(row("gelbooru").getByRole("button", { name: "Test Gelbooru" }));
    await vi.waitFor(() => expect(row("gelbooru").getByText("Connected")).toBeDefined());
    expect(testConnection).toHaveBeenCalledWith("gelbooru");
    expect(row("gelbooru").getByText("Ready")).toBeDefined();
    await vi.advanceTimersByTimeAsync(4100);
    expect(row("gelbooru").queryByText("Connected")).toBeNull();
  });

  it("the gear opens the connection dialog", async () => {
    await renderCard(ALL());
    await fireEvent.click(row("danbooru").getByRole("button", { name: "Edit Danbooru" }));
    expect(await screen.findByRole("dialog")).toBeDefined();
  });

  it("a load error shows Unknown pills and Retry", async () => {
    const getConnections = vi.fn().mockRejectedValue(new Error("down"));
    const store = createConnections();
    render(SitesCard, { store, optionsStore: optionsStore(), api: { getConnections } as unknown as Api });
    await vi.waitFor(() => expect(store.error).toBe(true));
    expect(screen.getByText("Could not load sites")).toBeDefined();
    expect(row("danbooru").getByText("Unknown")).toBeDefined();
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(getConnections).toHaveBeenCalledTimes(2);
  });
});
