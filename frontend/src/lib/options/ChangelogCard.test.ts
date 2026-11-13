// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent, screen } from "@testing-library/svelte";
import ChangelogCard from "./ChangelogCard.svelte";

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

const status = (o: object = {}) => ({
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
  ...o,
});

const block = (title: string, extra: object = {}) => ({
  title,
  range: null,
  version: title.startsWith("v") ? title.slice(1) : null,
  date: "2026-11-13",
  groups: [{ kind: "Added", items: [`${title} item`] }],
  total: 1,
  more: 0,
  more_url: null,
  ...extra,
});

const page = (o: object = {}) => ({
  channel: "main",
  unavailable: false,
  stale: false,
  whats_new: null,
  history: [block("v1.2.4"), block("v1.2.3")],
  has_more: false,
  ...o,
});

describe("ChangelogCard", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.api = {
      getUpdateStatus: vi.fn().mockResolvedValue(status({ available: false })),
      putUpdateSettings: vi.fn(),
      getUpdateChangelog: vi.fn().mockResolvedValue(page()),
    };
  });

  it("shows date and channel badge; newest open, others closed", async () => {
    const { container } = render(ChangelogCard);
    await screen.findByText("v1.2.4 item");
    expect(screen.getAllByText("Main").length).toBeGreaterThan(2);
    expect(screen.getAllByText(/2026/).length).toBe(2);
    const details = [...container.querySelectorAll("details")];
    expect(details.map((d) => d.open)).toEqual([true, false]);
  });

  it("closes every release card when the pinned What's new card shows", async () => {
    hoisted.api.getUpdateChangelog.mockResolvedValue(
      page({ whats_new: block("What's new", { version: null, range: "1.2.3 → 1.2.4" }) }),
    );
    const { container } = render(ChangelogCard);
    expect(await screen.findByText("What's new since your version")).toBeTruthy();
    expect([...container.querySelectorAll("details")].every((d) => !d.open)).toBe(true);
  });

  it("toggle switches the viewed channel without changing the update channel", async () => {
    render(ChangelogCard);
    await screen.findByText("v1.2.4 item");
    await fireEvent.click(screen.getByRole("button", { name: "Changelog Dev" }));
    await vi.waitFor(() =>
      expect(hoisted.api.getUpdateChangelog).toHaveBeenLastCalledWith({ channel: "dev", refresh: false, offset: 0, limit: 10 }),
    );
    expect(hoisted.api.putUpdateSettings).not.toHaveBeenCalled();
  });

  it("Load more appends, dedupes a repeated tag and hides at the end", async () => {
    hoisted.api.getUpdateChangelog
      .mockResolvedValueOnce(page({ has_more: true }))
      .mockResolvedValueOnce(page({ history: [block("v1.2.3"), block("v1.2.2")], has_more: false }));
    render(ChangelogCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await screen.findByText("v1.2.2 item");
    expect(screen.getAllByText("v1.2.3 item").length).toBe(1);
    expect(hoisted.api.getUpdateChangelog).toHaveBeenLastCalledWith({ channel: "main", offset: 2, limit: 10 });
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("keeps shown cards and offers Retry when Load more fails", async () => {
    hoisted.api.getUpdateChangelog
      .mockResolvedValueOnce(page({ has_more: true }))
      .mockRejectedValueOnce(new Error("boom"));
    render(ChangelogCard);
    await fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByText("v1.2.4 item")).toBeTruthy();
  });

  it("shows the check-off note and no Load more", async () => {
    hoisted.api.getUpdateStatus.mockResolvedValue(status({ check_enabled: false }));
    render(ChangelogCard);
    expect(await screen.findByText("Update check is off. Showing saved data.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("shows Changelog unavailable with Retry", async () => {
    hoisted.api.getUpdateChangelog.mockResolvedValue(page({ unavailable: true, history: [] }));
    render(ChangelogCard);
    expect(await screen.findByText(/Changelog unavailable/)).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(hoisted.api.getUpdateChangelog).toHaveBeenCalledTimes(2);
  });

  it("does not fetch while its section is not open (Options search)", async () => {
    render(ChangelogCard, { active: false });
    await Promise.resolve();
    expect(hoisted.api.getUpdateChangelog).not.toHaveBeenCalled();
    expect(hoisted.api.getUpdateStatus).not.toHaveBeenCalled();
  });
});
