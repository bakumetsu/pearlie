// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { createRawSnippet } from "svelte";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/svelte";
import AppShell from "./AppShell.svelte";
import { isActive, hidesBars, isDeep, titleFor, shellEnabled, TABS } from "./nav";
import { undoToast } from "$lib/ui/undoToast";
import { toasts } from "$lib/stores/toasts.svelte";
import { sfw } from "$lib/stores/sfw.svelte";

afterEach(() => {
  cleanup();
  toasts.dismiss();
  sfw?.set(false);
});

const body = createRawSnippet(() => ({ render: () => `<main>screen</main>` }));
const mount = (current: string, queueBadge?: number, onnavigate = vi.fn()) =>
  render(AppShell, { current, queueBadge, onnavigate, children: body });

describe("nav helpers", () => {
  it("has today's six tabs and keeps Library lit on library_*", () => {
    expect(TABS.map((t) => t.label)).toEqual(["Discover", "Home", "Library", "Queue", "Trash", "Options"]);
    expect(isActive("library", "library_images")).toBe(true);
    expect(isActive("home", "library")).toBe(false);
  });
  it("hides bars on the reader only; back arrow on deep pages", () => {
    expect(hidesBars("read")).toBe(true);
    expect(hidesBars("read-web")).toBe(true);
    expect(hidesBars("item")).toBe(false);
    expect(isDeep("item")).toBe(true);
    expect(isDeep("queue")).toBe(false);
    expect(titleFor("queue")).toBe("Queue");
  });
  it("flag is off unless set to 1 or true", () => {
    expect(shellEnabled(undefined)).toBe(false);
    expect(shellEnabled("0")).toBe(false);
    expect(shellEnabled("1")).toBe(true);
    expect(shellEnabled("true")).toBe(true);
  });
});

describe("AppShell", () => {
  it("renders both bars with six links each and marks the active one", () => {
    mount("queue", 3);
    const navs = screen.getAllByRole("navigation", { name: "Main" });
    expect(navs).toHaveLength(2);
    for (const nav of navs) {
      expect(within(nav).getAllByRole("link")).toHaveLength(6);
      expect(within(nav).getByRole("link", { name: /Queue/ }).getAttribute("aria-current")).toBe("page");
    }
    expect(screen.getByText("screen")).toBeTruthy();
  });

  it("calls onnavigate when a tab is clicked", async () => {
    const onnavigate = vi.fn((e: Event) => e.preventDefault());
    mount("home", undefined, onnavigate);
    await fireEvent.click(within(screen.getAllByRole("navigation")[0]).getByRole("link", { name: /Trash/ }));
    expect(onnavigate).toHaveBeenCalledOnce();
  });

  it("hides the bars on the reader", () => {
    mount("read");
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.getByText("screen")).toBeTruthy();
  });

  it("shows a back arrow on deep pages and calls history.back", async () => {
    const back = vi.spyOn(history, "back").mockImplementation(() => {});
    mount("item");
    await fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(back).toHaveBeenCalledOnce();
    back.mockRestore();
    cleanup();
    mount("queue");
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
  });

  it("SFW eye toggles the existing store (one per bar)", async () => {
    mount("home");
    const eyes = screen.getAllByRole("button", { name: "Hide media (SFW mode)" });
    expect(eyes).toHaveLength(2);
    await fireEvent.click(eyes[0]);
    expect(sfw?.on).toBe(true);
    expect(screen.getAllByRole("button", { name: "Show media (SFW off)" })[0].getAttribute("aria-pressed")).toBe("true");
  });
});

describe("ToastRegion", () => {
  it("is a polite live region; Undo runs the action and dismisses", async () => {
    mount("home");
    const region = document.querySelector("[data-toast-region]")!;
    expect(region.getAttribute("aria-live")).toBe("polite");
    const onundo = vi.fn();
    undoToast("Moved to trash", onundo);
    expect(await screen.findByText("Moved to trash")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(onundo).toHaveBeenCalledOnce();
    expect(toasts.current).toBeNull();
  });

  it("shows the queued count", async () => {
    mount("home");
    toasts.push({ kind: "info", message: "one" });
    toasts.push({ kind: "info", message: "two" });
    expect(await screen.findByText("+1")).toBeTruthy();
  });
});
