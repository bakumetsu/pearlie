// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { tick } from "svelte";
import { render, cleanup } from "@testing-library/svelte";
import Options from "./Options.svelte";
import type { Router, Match } from "../lib/router";

const hoisted = vi.hoisted(() => ({ router: null as unknown }));

vi.mock("../lib/ctx", () => ({ getRouter: () => hoisted.router }));

// ── Mocks ─────────────────────────────────────────────────────────

function makeMatch(overrides: Partial<Match> = {}): Match {
  return {
    name: "options",
    params: {},
    query: new URLSearchParams(),
    path: "/options",
    ...overrides,
  };
}

function mockRouter(navigateSpy?: ReturnType<typeof vi.fn>): Router {
  return {
    current: () => makeMatch(),
    navigate: navigateSpy ?? vi.fn(),
    canGoBack: () => false,
    subscribe: () => () => {},
    destroy: () => {},
  };
}

/**
 * Mock window.matchMedia for phone/desktop switching.
 */
function mockMatchMedia(matches: boolean) {
  const listeners: Array<(e: { matches: boolean }) => void> = [];
  const mq = {
    matches,
    media: "(max-width: 767px)",
    addEventListener: vi.fn((_type: string, fn: (e: { matches: boolean }) => void) => {
      listeners.push(fn);
    }),
    removeEventListener: vi.fn((_type: string, fn: (e: { matches: boolean }) => void) => {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    }),
    dispatchEvent: vi.fn(),
    onchange: null,
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mq));
  return mq;
}

// ── Setup / teardown ──────────────────────────────────────────────

let navSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  navSpy = vi.fn();
  hoisted.router = mockRouter(navSpy);
  mockMatchMedia(false); // default: desktop
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────

describe("Options", () => {
  it("renders all 12 sections in the list (desktop, no search)", () => {
    render(Options, {
      props: { match: makeMatch() },
    });

    const rows = document.querySelectorAll("button[data-section]");
    expect(rows.length).toBe(12);

    const labels = Array.from(rows).map((r) =>
      r.querySelector(".section-row-label")?.textContent?.trim(),
    );
    expect(labels).toContain("General");
    expect(labels).toContain("Viewing");
    expect(labels).toContain("Content filter");
    expect(labels).toContain("Rules");
    expect(labels).toContain("Sources");
    expect(labels).toContain("Library");
    expect(labels).toContain("Trash");
    expect(labels).toContain("Update");
    expect(labels).toContain("Logs");
    expect(labels).toContain("About");
  });

  it("search shows 'Nothing found' when no match", async () => {
    render(Options, {
      props: { match: makeMatch() },
    });

    const input = document.querySelector<HTMLInputElement>(
      'input[aria-label="Search options"]',
    )!;
    const nativeSetter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!;
    nativeSetter.call(input, "zzzz_nonexistent");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();

    const noResults = document.querySelector(".no-results");
    expect(noResults?.textContent?.trim()).toBe("Nothing found");
  });

  it("phone: /options shows list only (no pane)", () => {
    mockMatchMedia(true);

    render(Options, {
      props: { match: makeMatch() },
    });

    // Should have the phone-list layout
    expect(document.querySelector(".phone-list")).toBeTruthy();
    // Should NOT have the desktop sidebar or pane
    expect(document.querySelector(".sidebar")).toBeNull();
    expect(document.querySelector(".pane")).toBeNull();
    // Search present
    expect(document.querySelector('input[aria-label="Search options"]')).toBeTruthy();
    // Section rows present
    expect(document.querySelectorAll("button[data-section]").length).toBe(12);
  });

  it("phone: /options/viewing shows section + back button", () => {
    mockMatchMedia(true);

    render(Options, {
      props: {
        match: makeMatch({
          params: { section: "viewing" },
          path: "/options/viewing",
        }),
      },
    });

    expect(document.querySelector(".phone-section")).toBeTruthy();

    const backBtn = document.querySelector<HTMLButtonElement>(
      'button[aria-label="Back to options"]',
    );
    expect(backBtn).toBeTruthy();

    // Section title shown
    const title = document.querySelector(".phone-title");
    expect(title?.textContent?.trim()).toBe("Viewing");
  });

  it("phone: back button navigates to /options", async () => {
    mockMatchMedia(true);

    render(Options, {
      props: {
        match: makeMatch({
          params: { section: "viewing" },
          path: "/options/viewing",
        }),
      },
    });

    const backBtn = document.querySelector<HTMLButtonElement>(
      'button[aria-label="Back to options"]',
    )!;
    backBtn.click();
    await tick();

    expect(navSpy).toHaveBeenCalledWith("/options");
  });

  it("remembers last section in localStorage", () => {
    const store: Record<string, string> = {
      "pearlie.options.section": "viewing",
    };
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
    });

    render(Options, {
      props: { match: makeMatch() },
    });

    // Desktop, no section param → should show "Viewing" as active
    const activeRow = document.querySelector<HTMLButtonElement>(
      'button[data-section][aria-current="page"]',
    );
    expect(activeRow).toBeTruthy();
    expect(
      activeRow?.querySelector(".section-row-label")?.textContent?.trim(),
    ).toBe("Viewing");
  });

  it("marks LATER sections with a LATER tag", () => {
    render(Options, { props: { match: makeMatch() } });
    const tags = document.querySelectorAll("button[data-section] .later-tag");
    expect(tags.length).toBe(1);
  });

  it("'/' focuses the search box", () => {
    render(Options, { props: { match: makeMatch() } });
    const input = document.querySelector<HTMLInputElement>('input[aria-label="Search options"]')!;
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true }));
    expect(document.activeElement).toBe(input);
  });

  it("Escape clears the search", async () => {
    render(Options, { props: { match: makeMatch() } });
    const input = document.querySelector<HTMLInputElement>('input[aria-label="Search options"]')!;
    input.value = "view";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await tick();
    expect(input.value).toBe("");
    expect(document.querySelectorAll("button[data-section]").length).toBe(12);
  });

  it("ArrowDown moves focus to the next section row", () => {
    render(Options, { props: { match: makeMatch() } });
    const rows = document.querySelectorAll<HTMLButtonElement>("button[data-section]");
    rows[0].focus();
    rows[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.activeElement).toBe(rows[1]);
  });
});
