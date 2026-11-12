// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ConnectionRows from "./ConnectionRows.svelte";
import { createConnections } from "../stores/connections.svelte";
import type { Api, ConnectionsOut, ConnectionOut, ConnectionTest } from "../api/client";

const names = [
  { key: "danbooru", label: "Danbooru" },
  { key: "nhentai", label: "nhentai" },
];

function conn(name: string, fields: ConnectionOut["fields"]): ConnectionOut {
  return {
    name,
    address: "https://example.test",
    key: "missing",
    address_fixed: true,
    address_locked: true,
    key_locked: false,
    fields,
    restart_needed: false,
  };
}

function makeData(): ConnectionsOut {
  return {
    can_store: true,
    connections: [
      conn("danbooru", [
        { id: "login", label: "Login", state: "missing", locked: false, primary: false },
        { id: "api_key", label: "API key", state: "set", locked: false, primary: true },
      ]),
      conn("nhentai", [
        { id: "cookie", label: "Cookie", state: "missing", locked: false, primary: true },
        { id: "user_agent", label: "User-Agent", state: "missing", locked: true, primary: false },
      ]),
    ],
  };
}

async function open(label: string) {
  const data = makeData();
  const putConnection = vi.fn().mockImplementation((name: string) =>
    Promise.resolve(data.connections.find((c) => c.name === name)),
  );
  const testConnection = vi.fn().mockResolvedValue({ ok: true, message: "connected" } as ConnectionTest);
  const api = { getConnections: vi.fn().mockResolvedValue(data), putConnection, testConnection } as unknown as Api;
  const store = createConnections();
  render(ConnectionRows, { title: "Site access", names, store, api });
  await vi.waitFor(() => expect(store.data).not.toBeNull());
  fireEvent.click(screen.getByRole("button", { name: `Edit ${label}` }));
  await screen.findByRole("dialog");
  return { putConnection, testConnection, store };
}

afterEach(() => cleanup());

describe("per-site credential fields", () => {
  it("renders one input per field with its set/missing chip", async () => {
    await open("Danbooru");
    expect(document.getElementById("conn-f-login")).not.toBeNull();
    expect(document.getElementById("conn-f-api_key")).not.toBeNull();
    expect(screen.getByText("Login")).toBeDefined();
    expect(screen.getByText("API key")).toBeDefined();
    expect(document.getElementById("conn-key")).toBeNull();
  });

  it("secret fields are password inputs, others text, all empty", async () => {
    await open("Danbooru");
    const login = document.getElementById("conn-f-login") as HTMLInputElement;
    const key = document.getElementById("conn-f-api_key") as HTMLInputElement;
    expect(key.type).toBe("password");
    expect(login.type).toBe("text");
    expect(login.value).toBe("");
    expect(key.value).toBe("");
  });

  it("a field set in .env is disabled", async () => {
    await open("nhentai");
    expect((document.getElementById("conn-f-user_agent") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("set in .env")).toBeDefined();
  });

  it("saves only the typed fields, then tests, and never keeps the values", async () => {
    const { putConnection, testConnection } = await open("Danbooru");
    fireEvent.input(document.getElementById("conn-f-login") as HTMLInputElement, {
      target: { value: "alice" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(putConnection).toHaveBeenCalledWith("danbooru", { fields: { login: "alice" } }),
    );
    await vi.waitFor(() => expect(testConnection).toHaveBeenCalledWith("danbooru"));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.body.innerHTML).not.toContain("alice");
  });

  it("clearing one field asks first and sends clear_fields for that field only", async () => {
    const { putConnection } = await open("Danbooru");
    fireEvent.click(screen.getByRole("button", { name: "Clear API key" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm clear API key" }));
    await vi.waitFor(() =>
      expect(putConnection).toHaveBeenCalledWith("danbooru", { clear_fields: ["api_key"] }),
    );
  });

  it("field controls are at least 44px tall in CSS", async () => {
    const src = (await import("./ConnectionPopup.svelte?raw")).default as string;
    expect(src).toMatch(/\.row input\s*{[^}]*min-height:\s*44px/);
    expect(src).toMatch(/\.btn\s*{[^}]*min-height:\s*44px/);
  });
});
