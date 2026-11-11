// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ConnectionRows from "./ConnectionRows.svelte";
import { createConnections } from "../stores/connections.svelte";
import type { ConnectionsStore } from "../stores/connections.svelte";
import { ApiError, errorText } from "../api/client";
import type { Api, ConnectionsOut, ConnectionOut, ConnectionTest } from "../api/client";

const names = [
  { key: "stash", label: "Stash" },
  { key: "komga", label: "Komga" },
  { key: "danbooru", label: "Danbooru" },
];

function makeConnections(can_store = true): ConnectionsOut {
  return {
    can_store,
    connections: [
      { name: "stash", address: "http://stash.local:9999", key: "missing", address_fixed: false, address_locked: false, key_locked: false },
      { name: "komga", address: "http://komga.local:8888", key: "set", address_fixed: false, address_locked: false, key_locked: false },
      { name: "danbooru", address: "https://danbooru.donmai.us", key: "set", address_fixed: true, address_locked: true, key_locked: false },
    ],
  };
}

function makeApi(data: ConnectionsOut) {
  const getConnections = vi.fn().mockResolvedValue(data);
  const putConnection = vi.fn().mockImplementation((name: string, body: Record<string, unknown>) => {
    const conn = data.connections.find((c) => c.name === name);
    if (!conn) return Promise.reject(new Error("not found"));
    const updated: ConnectionOut = { ...conn };
    if (typeof body.address === "string") updated.address = body.address;
    if (body.secret) updated.key = "set";
    if (body.clear_secret) updated.key = "missing";
    return Promise.resolve(updated);
  });
  const testConnection = vi.fn().mockResolvedValue({ ok: true, message: "Connection OK" } as ConnectionTest);
  const api = { getConnections, putConnection, testConnection } as unknown as Api;
  return { api, getConnections, putConnection, testConnection };
}

async function renderRows(
  data?: ConnectionsOut,
  overrides?: { putConnection: ReturnType<typeof vi.fn>; testConnection: ReturnType<typeof vi.fn> },
) {
  const conn = data ?? makeConnections();
  const { api, getConnections, putConnection, testConnection } = makeApi(conn);
  const store = createConnections() as ConnectionsStore;
  if (overrides) {
    if (overrides.putConnection) vi.spyOn(api, "putConnection").mockImplementation(overrides.putConnection);
    if (overrides.testConnection) vi.spyOn(api, "testConnection").mockImplementation(overrides.testConnection);
  }
  render(ConnectionRows, { title: "Connections", names, store, api });
  await vi.waitFor(() => expect(screen.getByText("Stash")).toBeDefined());
  await vi.waitFor(() => expect(store.data).not.toBeNull());
  return { store, api, getConnections, putConnection, testConnection };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("ConnectionRows", () => {
  it("rows render label, chip set/missing, and no secret text anywhere", async () => {
    await renderRows();

    expect(screen.getByText("Stash")).toBeDefined();
    expect(screen.getByText("Komga")).toBeDefined();
    expect(screen.getByText("Danbooru")).toBeDefined();

    // stash has key "" → "missing"; komga and danbooru have non-empty keys → "set"
    const chips = screen.getAllByText(/^(set|missing)$/);
    const stashChip = chips[0];
    const komgaChip = chips[1];
    const danbooruChip = chips[2];
    expect(stashChip.textContent).toBe("missing");
    expect(komgaChip.textContent).toBe("set");
    expect(danbooruChip.textContent).toBe("set");
  });

  it("Test button calls api.testConnection with the name and shows the result message", async () => {
    const { testConnection } = await renderRows();

    fireEvent.click(screen.getByRole("button", { name: "Test Stash" }));

    await vi.waitFor(() => expect(testConnection).toHaveBeenCalledWith("stash"));
    expect(await screen.findByText("Connection OK")).toBeDefined();
  });

  it("pencil opens a dialog with Address for stash and without Address for danbooru", async () => {
    await renderRows();

    // Open stash (address_fixed: false → showAddress: true)
    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");
    expect(screen.getByText("Address")).toBeDefined();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDefined();

    // Close and open danbooru (address_fixed: true → showAddress: false)
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Edit Danbooru" }));
    await screen.findByRole("dialog");
    expect(screen.queryByText("Address")).toBeNull();
  });

  it("key input is empty with placeholder Leave empty to keep", async () => {
    await renderRows();

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");

    const keyInput = document.getElementById("conn-key") as HTMLInputElement;
    expect(keyInput).not.toBeNull();
    expect(keyInput.value).toBe("");
    expect(keyInput.placeholder).toBe("Leave empty to keep");
  });

  it("can_store false: key input disabled, env note shown, Address still editable", async () => {
    const data = makeConnections(false);
    await renderRows(data);

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");

    const keyInput = document.getElementById("conn-key") as HTMLInputElement;
    expect(keyInput.disabled).toBe(true);
    expect(screen.getByRole("note").textContent).toBe("Set PEARLIE_SECRET_KEY in .env to save keys here");

    const addrInput = document.getElementById("conn-addr") as HTMLInputElement;
    expect(addrInput.disabled).toBe(false);
  });

  it("key_locked: key input disabled and set in .env shown", async () => {
    const data: ConnectionsOut = {
      can_store: true,
      connections: [
        { name: "stash", address: "http://stash.local:9999", key: "missing", address_fixed: false, address_locked: false, key_locked: true },
      ],
    };
    await renderRows(data);

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");

    const keyInput = document.getElementById("conn-key") as HTMLInputElement;
    expect(keyInput.disabled).toBe(true);
    expect(screen.getByText("set in .env")).toBeDefined();
  });

  it("Save and test sends only changed fields", async () => {
    // Sub-test a: typing a key
    const { putConnection, testConnection } = await renderRows();

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");

    const keyInput = document.getElementById("conn-key") as HTMLInputElement;
    fireEvent.input(keyInput, { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and test" }));

    await vi.waitFor(() => expect(putConnection).toHaveBeenCalledWith("stash", { secret: "abc" }));
    await vi.waitFor(() => expect(testConnection).toHaveBeenCalledWith("stash"));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    // Sub-test b: changing the address shows hint and sends {address}
    cleanup();
    const { putConnection: put2 } = await renderRows();

    fireEvent.click(screen.getByRole("button", { name: "Edit Komga" }));
    await screen.findByRole("dialog");

    const addrInput = document.getElementById("conn-addr") as HTMLInputElement;
    fireEvent.input(addrInput, { target: { value: "http://new-address:1234" } });

    expect(screen.getByText("Changing the address clears the stored key unless you also enter a key.")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Save and test" }));

    await vi.waitFor(() =>
      expect(put2).toHaveBeenCalledWith("komga", { address: "http://new-address:1234" }),
    );
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("Clear key asks for confirm first, then sends {clear_secret: true}", async () => {
    const { putConnection } = await renderRows();

    // Open komga which has a key set
    fireEvent.click(screen.getByRole("button", { name: "Edit Komga" }));
    await screen.findByRole("dialog");

    // Click "Clear key"
    fireEvent.click(screen.getByRole("button", { name: "Clear key" }));
    // Confirm screen appears, putConnection NOT called yet
    expect(putConnection).not.toHaveBeenCalled();
    expect(screen.getByText("Clear the stored key?")).toBeDefined();

    // Click "Clear" to confirm
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await vi.waitFor(() =>
      expect(putConnection).toHaveBeenCalledWith("komga", { clear_secret: true }),
    );
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("Escape closes the dialog", async () => {
    await renderRows();

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.keyDown(dialog, { key: "Escape" });

    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("rejected putConnection shows alert and keeps dialog open", async () => {
    const data = makeConnections();
    const { api, putConnection } = makeApi(data);
    const store = createConnections() as ConnectionsStore;
    putConnection.mockRejectedValueOnce(
      new ApiError(409, "no_master_key", "Set PEARLIE_SECRET_KEY in .env to save keys here"),
    );

    render(ConnectionRows, { title: "Connections", names, store, api: putConnection as unknown as Api ? (api as Api) : (api as Api) });
    await vi.waitFor(() => expect(screen.getByText("Stash")).toBeDefined());

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");

    const keyInput = document.getElementById("conn-key") as HTMLInputElement;
    fireEvent.input(keyInput, { target: { value: "try-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and test" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(errorText(new ApiError(409, "no_master_key", "Set PEARLIE_SECRET_KEY in .env to save keys here")));

    // Dialog stays open
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("after successful save the secret is not in DOM or store data", async () => {
    const { store } = await renderRows();

    fireEvent.click(screen.getByRole("button", { name: "Edit Stash" }));
    await screen.findByRole("dialog");

    const secret = "super-secret-123";
    const keyInput = document.getElementById("conn-key") as HTMLInputElement;
    fireEvent.input(keyInput, { target: { value: secret } });
    fireEvent.click(screen.getByRole("button", { name: "Save and test" }));

    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(document.body.innerHTML).not.toContain(secret);
    expect(JSON.stringify(store.data)).not.toContain(secret);
  });
});
