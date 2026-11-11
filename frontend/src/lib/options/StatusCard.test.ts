// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/svelte";
import StatusCard from "./StatusCard.svelte";

const hoisted = vi.hoisted(() => ({ api: {} as { health: ReturnType<typeof vi.fn> } }));

vi.mock("../api/client", async (orig) => ({
  ...(await orig<typeof import("../api/client")>()),
  getApi: () => hoisted.api,
}));

const mockHealth = {
  stash: { state: "ok" },
  komga: { state: "down" },
  db: "ok",
  mounts: [{ name: "local", state: "ok" }],
  sites: [{ id: "danbooru", state: "not_configured" }],
};

beforeEach(() => {
  hoisted.api = {
    health: vi.fn().mockResolvedValue(mockHealth),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("StatusCard", () => {
  it("renders rows from mocked health with correct labels", async () => {
    render(StatusCard);

    await waitFor(() => {
      expect(screen.getByText("Stash")).toBeDefined();
    });

    const stashRow = screen.getByText("Stash").closest("li");
    expect(stashRow?.textContent).toContain("OK");

    const komgaRow = screen.getByText("Komga").closest("li");
    expect(komgaRow?.textContent).toContain("Down");

    const dbRow = screen.getByText("Database").closest("li");
    expect(dbRow?.textContent).toContain("OK");

    const danbooruRow = screen.getByText("danbooru").closest("li");
    expect(danbooruRow?.textContent).toContain("Not configured");

    expect(screen.getByText("Mount local")).toBeDefined();
  });

  it("shows Status unavailable on rejection", async () => {
    hoisted.api = {
      health: vi.fn().mockRejectedValue(new Error("network error")),
    };

    render(StatusCard);

    await waitFor(() => {
      expect(screen.getByText("Status unavailable.")).toBeDefined();
    });
  });
});
