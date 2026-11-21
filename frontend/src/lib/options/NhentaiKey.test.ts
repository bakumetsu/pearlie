// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ConnectionRows from "./ConnectionRows.svelte";
import popupSource from "./ConnectionPopup.svelte?raw";
import { createConnections } from "../stores/connections.svelte";
import type { Api, ConnectionsOut, ConnectionOut, ConnectionTest } from "../api/client";

const names = [{ key: "nhentai", label: "nhentai" }];

function nh(over: Partial<ConnectionOut> = {}, keyState: "set" | "missing" = "missing", cookie: "set" | "missing" = "missing"): ConnectionOut {
  return {
    name: "nhentai",
    address: "https://nhentai.net",
    key: keyState,
    address_fixed: true,
    address_locked: true,
    key_locked: false,
    fields: [
      { id: "api_key", label: "API key", state: keyState, locked: false, primary: true },
      { id: "cookie", label: "Cookie", state: cookie, locked: false, primary: false },
      { id: "user_agent", label: "User-Agent", state: "missing", locked: false, primary: false },
    ],
    ...over,
  };
}

async function setup(c: ConnectionOut, test: ConnectionTest = { ok: true, message: "Key works" }) {
  const data: ConnectionsOut = { can_store: true, connections: [c] };
  const putConnection = vi.fn().mockResolvedValue(c);
  const testConnection = vi.fn().mockResolvedValue(test);
  const api = { getConnections: vi.fn().mockResolvedValue(data), putConnection, testConnection } as unknown as Api;
  const store = createConnections();
  render(ConnectionRows, { title: "Site access", names, store, api });
  await vi.waitFor(() => expect(store.data).not.toBeNull());
  return { putConnection, testConnection };
}

async function openPopup() {
  fireEvent.click(screen.getByRole("button", { name: "Edit nhentai" }));
  await screen.findByRole("dialog");
}

afterEach(() => cleanup());

describe("nhentai row chip", () => {
  it.each([
    [nh(), "missing"],
    [nh({}, "set"), "set"],
    [nh({ auth: "ok" }, "set"), "ok"],
    [nh({ auth: "failed", reason: "invalid" }, "set"), "invalid"],
    [nh({ auth: "unchecked" }, "set"), "set"],
  ])("shows %# as a plain word", async (c, word) => {
    await setup(c);
    expect(document.querySelector(".row .chip")!.textContent).toBe(word);
  });
});

describe("nhentai key popup", () => {
  it("shows the key field first with an 8-dot placeholder and hides Cookie and User-Agent under Advanced", async () => {
    await setup(nh({}, "set"));
    await openPopup();
    const key = document.getElementById("conn-f-api_key") as HTMLInputElement;
    expect(key.type).toBe("password");
    expect(key.placeholder).toBe("•".repeat(8));
    expect(key.value).toBe("");
    expect(document.getElementById("conn-f-cookie")).toBeNull();
    const fold = screen.getByRole("button", { name: /Advanced/ });
    expect(fold.getAttribute("aria-expanded")).toBe("false");
    await fireEvent.click(fold);
    expect(fold.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById("conn-f-cookie")).not.toBeNull();
    expect(document.getElementById("conn-f-user_agent")).not.toBeNull();
  });

  it("opens Advanced when a cookie is already set", async () => {
    await setup(nh({}, "missing", "set"));
    await openPopup();
    expect(document.getElementById("conn-f-cookie")).not.toBeNull();
  });

  it("has a safe external link to the nhentai settings", async () => {
    await setup(nh());
    await openPopup();
    const link = screen.getByRole("link", { name: /nhentai API key settings/ }) as HTMLAnchorElement;
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
    expect(link.href).toContain("nhentai.net");
  });

  it("shows the rejected-key error linked to the field", async () => {
    await setup(nh({ auth: "failed", reason: "invalid" }, "set"));
    await openPopup();
    const err = screen.getByRole("alert");
    expect(err.textContent).toBe("nhentai rejected this key");
    expect(document.getElementById("conn-f-api_key")!.getAttribute("aria-describedby")).toBe(err.id);
  });

  it("saves the typed key, tests, closes on success and never keeps the key", async () => {
    const { putConnection, testConnection } = await setup(nh());
    await openPopup();
    fireEvent.input(document.getElementById("conn-f-api_key") as HTMLInputElement, {
      target: { value: "sekret-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(putConnection).toHaveBeenCalledWith("nhentai", { fields: { api_key: "sekret-key" } }),
    );
    await vi.waitFor(() => expect(testConnection).toHaveBeenCalledWith("nhentai"));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.body.innerHTML).not.toContain("sekret-key");
  });

  it("stays open when the check fails", async () => {
    const { testConnection } = await setup(nh(), { ok: false, message: "Key rejected by nhentai" });
    await openPopup();
    fireEvent.input(document.getElementById("conn-f-api_key") as HTMLInputElement, {
      target: { value: "bad" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(testConnection).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("dialog")).not.toBeNull();
  });

  it("emptying a touched, set key sends clear_fields for the key", async () => {
    const { putConnection } = await setup(nh({}, "set"));
    await openPopup();
    const key = document.getElementById("conn-f-api_key") as HTMLInputElement;
    fireEvent.input(key, { target: { value: "x" } });
    fireEvent.input(key, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(putConnection).toHaveBeenCalledWith("nhentai", { clear_fields: ["api_key"] }));
  });

  it("keeps 44 px touch targets on the link, fold, Save and Cancel", async () => {
    await setup(nh());
    await openPopup();
    // jsdom has no layout and drops scoped styles: assert the rule text in the source
    const css = popupSource;
    expect(css).toMatch(/\.btn\s*\{[^}]*min-height:\s*44px/);
    expect(css).toMatch(/\.btn\s*\{[^}]*min-width:\s*44px/);
    for (const el of [
      screen.getByRole("link", { name: /nhentai API key settings/ }),
      screen.getByRole("button", { name: /Advanced/ }),
      screen.getByRole("button", { name: "Save" }),
      screen.getByRole("button", { name: "Cancel" }),
    ]) {
      expect(el.classList.contains("btn")).toBe(true);
    }
  });
});
