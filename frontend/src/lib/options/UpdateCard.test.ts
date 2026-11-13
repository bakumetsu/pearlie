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

  it("shows the installed version with the short commit as a tooltip", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(
      makeStatus({ installed: { version: "0.4.0-dev", channel: "dev", commit: "abc1234def5678" } }),
    );
    render(UpdateCard);
    const el = await screen.findByText("0.4.0-dev");
    expect(el.getAttribute("title")).toBe("abc1234");
  });

  it("has no tooltip when the commit is absent", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(
      makeStatus({ installed: { version: "0.4.0-dev", channel: "dev", commit: "" } }),
    );
    render(UpdateCard);
    const el = await screen.findByText("0.4.0-dev");
    expect(el.hasAttribute("title")).toBe(false);
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

  it("status load fails: Retry button and Restarting strip show, Retry recovers", async () => {
    hoisted.api.health = vi.fn().mockRejectedValue(new Error("down"));
    hoisted.api.getUpdateStatus
      .mockRejectedValueOnce(new Error("Failed to fetch"))
      .mockResolvedValue(makeStatus());
    render(UpdateCard);
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect((await screen.findByRole("status")).textContent).toContain("Restarting");
    hoisted.api.health = vi.fn().mockResolvedValue({ status: "ok" });
    await fireEvent.click(retry);
    await screen.findByText("1.2.3");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
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

  it("Update button shows only the icon", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus({ can_apply: true }));

    render(UpdateCard);

    const btn = await screen.findByRole("button", { name: /^Update/ });
    const el = btn as HTMLButtonElement;
    expect(el.getAttribute("aria-label")?.startsWith("Update")).toBe(true);
    expect(el.textContent?.trim()).toBe("");
  });
});

describe("UpdateCard changelog", () => {
  afterEach(() => cleanup());

  const block = (title: string, items: string[], extra: object = {}) => ({
    title,
    range: null,
    version: null,
    groups: [{ kind: "Added", items }],
    total: items.length,
    more: 0,
    more_url: null,
    ...extra,
  });
  const changelog = (overrides: object = {}) => ({
    channel: "main",
    unavailable: false,
    stale: false,
    whats_new: block("What's new", ["Shiny thing"], { range: "1.2.3 → 1.2.4" }),
    history: [block("v1.2.4", ["Shiny thing"]), block("v1.2.3", ["Older thing"])],
    ...overrides,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.api = {
      getUpdateStatus: vi.fn().mockResolvedValue(makeStatus()),
      putUpdateSettings: vi.fn(),
      getUpdateChangelog: vi.fn().mockResolvedValue(changelog()),
    };
  });

  it("shows the What's new block with the installed to latest range", async () => {
    render(UpdateCard);
    expect(await screen.findByText("What's new")).toBeTruthy();
    expect(screen.getByText("1.2.3 → 1.2.4")).toBeTruthy();
    expect(screen.getAllByText("Shiny thing").length).toBeGreaterThan(0);
  });

  it("lists past versions collapsed, in the order the backend sent", async () => {
    const { container } = render(UpdateCard);
    await screen.findByText("What's new");
    const details = [...container.querySelectorAll("details")];
    expect(details.map((d) => d.querySelector("summary")?.textContent?.trim().split(" ")[0])).toEqual([
      "v1.2.4",
      "v1.2.3",
    ]);
    expect(details.every((d) => !d.open)).toBe(true);
  });

  it("defaults the toggle to the current channel and switches the view", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(makeStatus({ channel: "dev" }));
    render(UpdateCard);
    const dev = await screen.findByRole("button", { name: "Changelog Dev" });
    expect(dev.getAttribute("aria-pressed")).toBe("true");
    expect(hoisted.api.getUpdateChangelog).toHaveBeenCalledWith({ channel: "dev", refresh: false });
    await fireEvent.click(screen.getByRole("button", { name: "Changelog Main" }));
    expect(hoisted.api.getUpdateChangelog).toHaveBeenLastCalledWith({ channel: "main", refresh: false });
  });

  it("refreshes the changelog on Check now", async () => {
    render(UpdateCard);
    await screen.findByText("What's new");
    await fireEvent.click(screen.getByRole("button", { name: "Check for updates" }));
    await vi.waitFor(() =>
      expect(hoisted.api.getUpdateChangelog).toHaveBeenLastCalledWith({ channel: "main", refresh: true }),
    );
  });

  it("shows a quiet message when the changelog is unavailable", async () => {
    hoisted.api.getUpdateChangelog.mockResolvedValue(
      changelog({ unavailable: true, whats_new: null, history: [] }),
    );
    render(UpdateCard);
    expect(await screen.findByText("Changelog unavailable.")).toBeTruthy();
  });

  it("links to GitHub when a version has more changes than shown", async () => {
    hoisted.api.getUpdateChangelog.mockResolvedValue(
      changelog({
        whats_new: null,
        history: [block("v1.2.4", ["A"], { more: 7, more_url: "https://github.com/x/compare/a...b" })],
      }),
    );
    render(UpdateCard);
    const link = await screen.findByText("+ 7 more on GitHub");
    expect(link.getAttribute("href")).toBe("https://github.com/x/compare/a...b");
  });

  it("keeps the card working when the changelog call fails", async () => {
    hoisted.api.getUpdateChangelog.mockRejectedValue(new Error("boom"));
    render(UpdateCard);
    expect(await screen.findByText("1.2.3")).toBeTruthy();
    expect(screen.queryByText("What's new")).toBeNull();
  });
});
