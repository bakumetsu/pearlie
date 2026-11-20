// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, waitFor, fireEvent } from "@testing-library/svelte";
import SidePanel from "./SidePanel.svelte";
import css from "./SidePanel.svelte?raw";
import { API_CONTEXT_KEY, ApiError } from "../api/client";
import type { Api } from "../api/client";

afterEach(cleanup);

const row = (n: number, extra: Record<string, unknown> = {}) => ({ id: String(n), source: "nhentai", title: "Title " + n, author: "Au " + n, thumb_url: "/t" + n, ...extra });
const none = vi.fn(async () => ({ items: [] }));

function mount(api: Record<string, unknown>, onopen = vi.fn()) {
  const ctx = new Map<unknown, unknown>([[API_CONTEXT_KEY, api as unknown as Api]]);
  return { onopen, ...render(SidePanel, { props: { source: "nhentai", id: "1", onopen }, context: ctx }) };
}

describe("SidePanel", () => {
  it("shows skeletons while loading, then rows with the saved check", async () => {
    let done: (v: unknown) => void = () => {};
    const recommend = vi.fn(() => new Promise((r) => (done = r)));
    const { container, getByText, getByLabelText } = mount({ recommend, recommendRandom: none });
    expect(container.querySelectorAll(".skel").length).toBeGreaterThan(0);
    done({ items: [row(2, { saved: { kind: "book", id: "x" } }), row(3)] });
    await waitFor(() => getByText("Title 2"));
    expect(getByLabelText("In library")).toBeTruthy();
    expect(getByText("Au 3")).toBeTruthy();
  });

  it("shows the empty texts", async () => {
    const { getByText } = mount({ recommend: none, recommendRandom: none });
    await waitFor(() => getByText("Nothing similar found."));
    expect(getByText("Nothing to show.")).toBeTruthy();
  });

  it("shows Could not load with a working Retry", async () => {
    const recommend = vi.fn().mockRejectedValueOnce(new ApiError(502, "upstream", "x")).mockResolvedValue({ items: [row(5)] });
    const { getByText, getByRole } = mount({ recommend, recommendRandom: none });
    await waitFor(() => getByText("Could not load."));
    await fireEvent.click(getByRole("alert").querySelector("button")!);
    await waitFor(() => getByText("Title 5"));
    expect(recommend).toHaveBeenCalledTimes(2);
  });

  it("rate_limited shows the wait text, disables Retry for retry_after and does not retry by itself", async () => {
    vi.useFakeTimers();
    try {
      const err = new ApiError(429, "rate_limited", "slow");
      err.retryAfter = 2;
      const recommend = vi.fn().mockRejectedValue(err);
      const { getByText, getByRole } = mount({ recommend, recommendRandom: none });
      await vi.waitFor(() => getByText("Try again in a moment."));
      const btn = getByRole("alert").querySelector("button")!;
      expect(btn.disabled).toBe(true);
      await vi.advanceTimersByTimeAsync(2500);
      expect(btn.disabled).toBe(false);
      expect(recommend).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shuffle calls Random again and is disabled while the call runs; row tap calls onopen", async () => {
    let done: (v: unknown) => void = () => {};
    const recommendRandom = vi
      .fn()
      .mockResolvedValueOnce({ items: [row(7)] })
      .mockImplementationOnce(() => new Promise((r) => (done = r)));
    const { getByText, getByLabelText, onopen } = mount({ recommend: none, recommendRandom });
    await waitFor(() => getByText("Title 7"));
    const shuffle = getByLabelText("Shuffle") as HTMLButtonElement;
    await fireEvent.click(shuffle);
    expect(shuffle.disabled).toBe(true);
    done({ items: [row(8)] });
    await waitFor(() => getByText("Title 8"));
    await fireEvent.click(getByText("Title 8"));
    expect(onopen).toHaveBeenCalledWith(expect.objectContaining({ id: "8" }));
  });
  it("uses 121 px thumbnails from 900 px", () => {
    expect(css).toMatch(/@media \(min-width: 900px\)[^@]*grid-template-columns:\s*121px 1fr/);
    expect(css).toMatch(/\.mth\s*\{[^}]*width:\s*121px/);
  });
});
