// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent, screen } from "@testing-library/svelte";
import UpdateCard from "./UpdateCard.svelte";

const hoisted = vi.hoisted(() => ({
  api: {} as Record<string, ReturnType<typeof vi.fn>>,
}));

vi.mock("../api/client", async (orig) => ({
  ...(await orig<typeof import("../api/client")>()),
  getApi: () => hoisted.api,
}));

vi.mock("../stores/toasts.svelte", () => ({
  toasts: { push: vi.fn() },
}));

interface UpdateStatus {
  installed: { version: string; channel: string; commit: string };
  latest: { version: string; commit: string; url: string } | null;
  available: boolean;
  checked_at: string;
  check_enabled: boolean;
  channel: string;
  state: string;
  step: string | null;
  error: string | null;
  retry_after: number | null;
  can_apply: boolean;
}

function makeStatus(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    installed: { version: "1.2.3", channel: "main", commit: "abc1234" },
    latest: { version: "1.2.4", commit: "def5678", url: "https://example.com/v1.2.4" },
    available: true,
    checked_at: "2026-06-01T12:00:00Z",
    check_enabled: true,
    channel: "main",
    state: "update_available",
    step: null,
    error: null,
    retry_after: null,
    can_apply: true,
    ...overrides,
  };
}

describe("UpdateCard", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.api = {
      getUpdateStatus: vi.fn(),
      putUpdateSettings: vi.fn(),
    };
  });

  it("renders Installed version, channel pill, and Latest version", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus());

    render(UpdateCard);

    expect(await screen.findByText("1.2.3")).toBeTruthy();
    expect(screen.getByText("main")).toBeTruthy();
    expect(await screen.findByText("1.2.4")).toBeTruthy();
  });

  it("Update opens the confirm sheet; Cancel closes it without applying", async () => {
    hoisted.api.applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
    hoisted.api.health = vi.fn().mockResolvedValue({ status: "ok" });
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus());
    render(UpdateCard);
    await fireEvent.click(await screen.findByRole("button", { name: /^Update/ }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(hoisted.api.applyUpdate).not.toHaveBeenCalled();
  });

  it("Confirm calls applyUpdate and shows the progress strip", async () => {
    hoisted.api.applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
    hoisted.api.health = vi.fn().mockResolvedValue({ status: "ok" });
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus());
    render(UpdateCard);
    await fireEvent.click(await screen.findByRole("button", { name: /^Update/ }));
    await fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(hoisted.api.applyUpdate).toHaveBeenCalledTimes(1);
    const strip = await screen.findByRole("status");
    expect(strip).toBeTruthy();
  });

  it("failed_rollback status shows a persistent alert", async () => {
    hoisted.api.applyUpdate = vi.fn().mockResolvedValue({ state: "running" });
    hoisted.api.health = vi.fn().mockResolvedValue({ status: "ok" });
    hoisted.api.getUpdateStatus = vi.fn().mockResolvedValue(
      makeStatus({ state: "failed_rollback", error: "bad" }),
    );
    render(UpdateCard);
    await fireEvent.click(await screen.findByRole("button", { name: /^Update/ }));
    await fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await vi.waitFor(
      () => expect(screen.queryByRole("alert")).toBeTruthy(),
      { timeout: 5000 },
    );
  }, 10000);

  it("shows 'Switch to X' when channel differs from installed", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus({ channel: "dev" }));
    render(UpdateCard);
    expect(await screen.findByRole("button", { name: "Switch to 1.2.4" })).toBeTruthy();
  });

  it("shows 'Up to date' when no update is available", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(
      makeStatus({
        latest: { version: "1.2.3", commit: "abc1234", url: "https://example.com/v1.2.3" },
        available: false,
        state: "up_to_date",
      }),
    );

    render(UpdateCard);

    expect(await screen.findByText("Up to date")).toBeTruthy();
  });

  it("shows 'Check later' on rate_limited with no latest", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(
      makeStatus({
        latest: null,
        error: "rate_limited",
        available: false,
        state: "rate_limited",
      }),
    );

    render(UpdateCard);

    expect(await screen.findByText("Check later")).toBeTruthy();
  });

  it("disables Update button with title when can_apply is false", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus({ can_apply: false }));

    render(UpdateCard);

    const btn = await screen.findByRole("button", { name: /^Update/ });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(btn.getAttribute("title")).toBe("Updating is not available here");
  });

  it("opens the confirm sheet when Update is clicked and can_apply is true", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus());

    render(UpdateCard);

    const btn = await screen.findByRole("button", { name: /^Update/ });
    expect((btn as HTMLButtonElement).disabled).toBe(false);

    await fireEvent.click(btn);
    expect(screen.getByRole("dialog", { name: "Confirm update" })).toBeTruthy();
  });

  it('calls putUpdateSettings with {channel:"dev"} when "Dev" is clicked', async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus());
    hoisted.api.putUpdateSettings.mockResolvedValue(undefined);

    render(UpdateCard);

    const devBtn = await screen.findByRole("button", { name: "Dev" });
    await fireEvent.click(devBtn);
    expect(hoisted.api.putUpdateSettings).toHaveBeenCalledWith({ channel: "dev" });
  });

  it("calls getUpdateStatus with {refresh:true,manual:true} on the check button", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus());

    render(UpdateCard);

    const checkBtn = await screen.findByRole("button", { name: "Check for updates" });
    await fireEvent.click(checkBtn);
    expect(hoisted.api.getUpdateStatus).toHaveBeenCalledWith({ refresh: true, manual: true });
  });
});
