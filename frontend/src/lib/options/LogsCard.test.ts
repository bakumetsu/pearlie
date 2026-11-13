// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent, screen, waitFor } from "@testing-library/svelte";
import LogsCard from "./LogsCard.svelte";
import src from "./LogsCard.svelte?raw";
import { toasts } from "../stores/toasts.svelte";

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

const line = (n: number, level = "info", text = `line ${n}`) => ({
  ts: `2026-11-13 10:00:${String(n).padStart(2, "0")}.000`,
  level,
  logger: "pearlie.test",
  text,
});

const files = (extra = {}) => ({
  debug: false,
  keep_days: 7,
  dir_name: "logs",
  cap_bytes: 20971520,
  files: [
    { date: "2026-11-13", size_bytes: 2048, lines: 5 },
    { date: "2026-11-12", size_bytes: 100, lines: 1 },
  ],
  ...extra,
});

describe("LogsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.api = {
      getLogs: vi.fn().mockResolvedValue(files()),
      getLogLines: vi.fn().mockResolvedValue({
        date: "2026-11-13",
        level: "info",
        lines: [line(2, "error", "boom"), line(1)],
        next_cursor: null,
      }),
      putLogDebug: vi.fn().mockResolvedValue({ debug: true }),
      logDownloadUrl: vi.fn((d: string, l: string) => `/api/logs/${d}/download?level=${l}`),
    };
  });
  afterEach(() => cleanup());

  it("loads the newest day at info level and shows the lines", async () => {
    render(LogsCard);
    expect(await screen.findByText("boom")).toBeTruthy();
    expect(hoisted.api.getLogLines).toHaveBeenCalledWith("2026-11-13", { level: "info", limit: 200 });
    expect(screen.getByText("10:00:02")).toBeTruthy();
    expect(screen.getByText("line 1")).toBeTruthy();
    expect(screen.queryByText("Load older")).toBeNull();
  });

  it("reloads from the start when the level changes", async () => {
    render(LogsCard);
    await screen.findByText("boom");
    await fireEvent.click(screen.getByRole("button", { name: "Error" }));
    await waitFor(() =>
      expect(hoisted.api.getLogLines).toHaveBeenLastCalledWith("2026-11-13", { level: "error", limit: 200 }),
    );
    expect(screen.getByRole("button", { name: "Error" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Info" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("reloads when another day is picked", async () => {
    render(LogsCard);
    await screen.findByText("boom");
    const select = screen.getByLabelText("Day") as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: "2026-11-12" } });
    await waitFor(() =>
      expect(hoisted.api.getLogLines).toHaveBeenLastCalledWith("2026-11-12", { level: "info", limit: 200 }),
    );
  });

  it("appends older lines with the cursor", async () => {
    hoisted.api.getLogLines
      .mockResolvedValueOnce({ date: "2026-11-13", level: "info", lines: [line(5)], next_cursor: "123" })
      .mockResolvedValueOnce({ date: "2026-11-13", level: "info", lines: [line(4)], next_cursor: null });
    render(LogsCard);
    await screen.findByText("line 5");
    await fireEvent.click(screen.getByRole("button", { name: "Load older" }));
    expect(await screen.findByText("line 4")).toBeTruthy();
    expect(hoisted.api.getLogLines).toHaveBeenLastCalledWith("2026-11-13", {
      level: "info",
      cursor: "123",
      limit: 200,
    });
    expect(screen.getByText("line 5")).toBeTruthy();
    expect(screen.queryByText("Load older")).toBeNull();
  });

  it("copies the shown lines and says Copied", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(LogsCard);
    await screen.findByText("boom");
    await fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const text = writeText.mock.calls[0][0] as string;
    expect(text.split("\n")).toHaveLength(2);
    expect(text).toContain("ERROR  pearlie.test  boom");
    expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Copied" });
  });

  it("links Download to the day and level", async () => {
    render(LogsCard);
    await screen.findByText("boom");
    const a = screen.getByRole("link", { name: "Download" });
    expect(a.getAttribute("href")).toBe("/api/logs/2026-11-13/download?level=info");
    await fireEvent.click(screen.getByRole("button", { name: "Debug" }));
    expect(
      (screen.getByRole("link", { name: "Download" }) as HTMLAnchorElement).getAttribute("href"),
    ).toBe("/api/logs/2026-11-13/download?level=debug");
  });

  it("refresh reads the file list and lines again", async () => {
    render(LogsCard);
    await screen.findByText("boom");
    await fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(hoisted.api.getLogs).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(hoisted.api.getLogLines).toHaveBeenCalledTimes(2));
  });

  it("shows the empty state for a day with no lines at this level", async () => {
    hoisted.api.getLogLines.mockResolvedValue({ date: "2026-11-13", level: "error", lines: [], next_cursor: null });
    render(LogsCard);
    expect(await screen.findByText("No lines at this level for this day.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Copy" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows No logs yet when there are no files", async () => {
    hoisted.api.getLogs.mockResolvedValue(files({ files: [] }));
    render(LogsCard);
    expect(await screen.findByText("No logs yet.")).toBeTruthy();
    expect(hoisted.api.getLogLines).not.toHaveBeenCalled();
  });

  it("shows an error with Retry that loads again", async () => {
    hoisted.api.getLogLines.mockRejectedValueOnce(new Error("x"));
    render(LogsCard);
    expect(await screen.findByText("Could not load the log")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("boom")).toBeTruthy();
  });

  it("keeps the loaded lines when Load older fails", async () => {
    hoisted.api.getLogLines
      .mockResolvedValueOnce({ date: "2026-11-13", level: "info", lines: [line(5)], next_cursor: "9" })
      .mockRejectedValueOnce(new Error("x"));
    render(LogsCard);
    await screen.findByText("line 5");
    await fireEvent.click(screen.getByRole("button", { name: "Load older" }));
    expect(await screen.findByText("Could not load older lines.")).toBeTruthy();
    expect(screen.getByText("line 5")).toBeTruthy();
  });

  it("turns Debug on with the chip and reverts with a toast on failure", async () => {
    render(LogsCard);
    await screen.findByText("boom");
    const sw = screen.getByRole("switch", { name: "Debug" });
    expect(sw.getAttribute("aria-checked")).toBe("false");
    await fireEvent.click(sw);
    await waitFor(() => expect(hoisted.api.putLogDebug).toHaveBeenCalledWith(true));
    expect(await screen.findByText("Debug is on")).toBeTruthy();

    hoisted.api.putLogDebug.mockRejectedValueOnce(new Error("nope"));
    await fireEvent.click(screen.getByRole("switch", { name: "Debug" }));
    await waitFor(() =>
      expect(toasts.push).toHaveBeenCalledWith(expect.objectContaining({ kind: "error" })),
    );
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Debug" }).getAttribute("aria-checked")).toBe("true"),
    );
  });

  it("shows a line without a timestamp as a continuation and expands long lines", async () => {
    const long = "x".repeat(150);
    hoisted.api.getLogLines.mockResolvedValue({
      date: "2026-11-13",
      level: "info",
      lines: [
        { ts: "", level: "info", logger: "", text: "  File trace.py, line 3" },
        { ...line(1), text: long },
      ],
      next_cursor: null,
    });
    const { container } = render(LogsCard);
    await screen.findByText(long);
    expect(container.querySelector("li.cont")).toBeTruthy();
    const btn = container.querySelector("button.linebtn") as HTMLButtonElement;
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(container.querySelector(".text.clamp")).toBeTruthy();
    await fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(container.querySelector(".text.clamp")).toBeNull();
  });

  it("gives every toolbar control a label and a 44 px minimum size", async () => {
    const { container } = render(LogsCard);
    await screen.findByText("boom");
    const controls = container.querySelectorAll(".toolbar button, .toolbar a, .toolbar select");
    expect(controls.length).toBe(8);
    for (const c of controls) {
      expect(c.getAttribute("aria-label")).toBeTruthy();
    }
    // jsdom does not lay out scoped styles: assert the rules in the source
    for (const sel of [".day", ".seg", ".iconbtn", ".textbtn"]) {
      const block = src.slice(src.indexOf(`	${sel} {`));
      const body = block.slice(0, block.indexOf("}"));
      expect(body, sel).toMatch(/min-height: 44px/);
    }
  });
});
