// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent, screen, waitFor } from "@testing-library/svelte";
import DebugKeyCard from "./DebugKeyCard.svelte";
import { toasts } from "../stores/toasts.svelte";

vi.mock("../stores/toasts.svelte", () => ({
  toasts: { push: vi.fn() },
}));

const OFF = { state: "off", id: null, created_at: null, expires_at: null, last_used_at: null, uses_approx: 0 };
const future = () => new Date(Date.now() + 23 * 3600_000).toISOString();
const ACTIVE = {
  state: "active",
  id: "ab12cd34",
  created_at: new Date().toISOString(),
  expires_at: future(),
  last_used_at: null,
  uses_approx: 12,
};
const EXPIRED = { ...ACTIVE, state: "expired", expires_at: new Date(Date.now() - 2 * 3600_000).toISOString() };
const CREATED = { key: "pdk_secretvalue123", id: "ab12cd34", expires_at: future() };

const hoisted = vi.hoisted(() => ({
  api: {} as Record<string, ReturnType<typeof vi.fn>>,
}));
vi.mock("../api/client", async (orig) => ({
  ...(await orig<typeof import("../api/client")>()),
  getApi: () => hoisted.api,
}));

describe("DebugKeyCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.api = { getDebugKey: vi.fn(), createDebugKey: vi.fn(), deleteDebugKey: vi.fn() };
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the off state with the 24 hours lifetime selected", async () => {
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF);
    render(DebugKeyCard);
    expect(await screen.findByText(/Off\. Lets Claude read/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "24 hours" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Create key" })).toBeTruthy();
  });

  it("creates a key, shows it once with Copy, and Done hides it", async () => {
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF).mockResolvedValueOnce(ACTIVE);
    hoisted.api.createDebugKey.mockResolvedValueOnce(CREATED);
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "7 days" }));
    await fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByLabelText("Debug key, shown once")).toBeTruthy();
    expect(screen.getByText("pdk_secretvalue123")).toBeTruthy();
    expect(hoisted.api.createDebugKey).toHaveBeenCalledWith("7d");
    await fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText("pdk_secretvalue123")).toBeNull();
    expect(await screen.findByText("ab12cd34")).toBeTruthy();
  });

  it("Copy writes the key to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF).mockResolvedValueOnce(ACTIVE);
    hoisted.api.createDebugKey.mockResolvedValueOnce(CREATED);
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Create key" }));
    await fireEvent.click(await screen.findByRole("button", { name: "Copy key" }));
    expect(writeText).toHaveBeenCalledWith("pdk_secretvalue123");
    expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Copied" });
  });

  it("a blocked clipboard keeps the key visible and shows an error toast", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("no")) } });
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF).mockResolvedValueOnce(ACTIVE);
    hoisted.api.createDebugKey.mockResolvedValueOnce(CREATED);
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Create key" }));
    await fireEvent.click(await screen.findByRole("button", { name: "Copy key" }));
    expect(screen.getByText("pdk_secretvalue123")).toBeTruthy();
    expect(toasts.push).toHaveBeenCalledWith(expect.objectContaining({ kind: "error" }));
  });

  it("a failed create leaves the off state and shows an error toast", async () => {
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF);
    hoisted.api.createDebugKey.mockRejectedValueOnce(new Error("x"));
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Create key" }));
    await waitFor(() =>
      expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Could not create the key" }),
    );
    expect(screen.getByRole("button", { name: "Create key" })).toBeTruthy();
  });

  it("active state shows rows, approx. wording and asks before replacing", async () => {
    hoisted.api.getDebugKey.mockResolvedValueOnce(ACTIVE);
    render(DebugKeyCard);
    expect(await screen.findByText("about 12")).toBeTruthy();
    expect(screen.getByText("never")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "New key" }));
    expect(screen.getByText("Replace the current key?")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "New key" })).toBeTruthy();
  });

  it("Never creates a key without expiry and the active card warns", async () => {
    const NEVER = { ...ACTIVE, expires_at: null };
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF).mockResolvedValueOnce(NEVER);
    hoisted.api.createDebugKey.mockResolvedValueOnce({ ...CREATED, expires_at: null });
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Never" }));
    await fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(hoisted.api.createDebugKey).toHaveBeenCalledWith("never");
    expect(await screen.findByText(/It never expires/)).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText(/No expiry\. Revoke the key/)).toBeTruthy();
  });

  it("Revoke sends DELETE without a confirm and shows a toast", async () => {
    hoisted.api.getDebugKey.mockResolvedValueOnce(ACTIVE).mockResolvedValueOnce(OFF);
    hoisted.api.deleteDebugKey.mockResolvedValueOnce(undefined);
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Key revoked" }),
    );
    expect(hoisted.api.deleteDebugKey).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: "Create key" })).toBeTruthy();
  });

  it("expired state shows the chip and a Remove button", async () => {
    hoisted.api.getDebugKey.mockResolvedValueOnce(EXPIRED);
    render(DebugKeyCard);
    expect(await screen.findByText("Expired", { selector: ".chip" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove" })).toBeTruthy();
  });

  it("load error shows Retry, which loads again", async () => {
    hoisted.api.getDebugKey.mockRejectedValueOnce(new Error("x")).mockResolvedValueOnce(OFF);
    render(DebugKeyCard);
    expect(await screen.findByText("Could not load the key state")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: "Create key" })).toBeTruthy();
  });

  it("never writes the key to storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    hoisted.api.getDebugKey.mockResolvedValueOnce(OFF).mockResolvedValueOnce(ACTIVE);
    hoisted.api.createDebugKey.mockResolvedValueOnce(CREATED);
    render(DebugKeyCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Create key" }));
    await screen.findByText("pdk_secretvalue123");
    expect(setItem).not.toHaveBeenCalled();
  });
});
