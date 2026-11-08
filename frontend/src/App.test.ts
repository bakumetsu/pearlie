import { describe, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/svelte";
import App from "./App.svelte";

describe("App", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows Backend: ok when API succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok", db: "ok" }),
      }),
    );
    render(App);
    await screen.findByText("Backend: ok");
  });

  it("shows Backend unreachable when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));
    render(App);
    await screen.findByText("Backend unreachable");
  });
});
