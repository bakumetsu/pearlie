// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { tick } from "svelte";
import { render, cleanup } from "@testing-library/svelte";
import { screen, fireEvent } from "@testing-library/dom";
import Options from "./Options.svelte";
import type { Router, Match } from "../lib/router";

const hoisted = vi.hoisted(() => ({
  router: null as unknown,
  api: null as unknown,
}));

vi.mock("../lib/ctx", () => ({ getRouter: () => hoisted.router }));

vi.mock("../lib/api/client", async (orig) => ({
  ...((await orig()) as Record<string, unknown>),
  getApi: () => hoisted.api,
}));

// ── Helpers ─────────────────────────────────────────────────────────

function makeMatch(overrides: Partial<Match> = {}): Match {
  return {
    name: "options",
    params: { section: "rules" },
    query: new URLSearchParams(),
    path: "/options/rules",
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

function mockMatchMedia(matches: boolean) {
  const listeners: Array<(e: { matches: boolean }) => void> = [];
  const mq = {
    matches,
    media: "(max-width: 767px)",
    addEventListener: vi.fn(
      (_type: string, fn: (e: { matches: boolean }) => void) => {
        listeners.push(fn);
      }
    ),
    removeEventListener: vi.fn(
      (_type: string, fn: (e: { matches: boolean }) => void) => {
        const i = listeners.indexOf(fn);
        if (i >= 0) listeners.splice(i, 1);
      }
    ),
    dispatchEvent: vi.fn(),
    onchange: null,
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mq));
  return mq;
}

function makeApi() {
  return {
    getRules: vi.fn().mockResolvedValue({
      version: 3,
      base_list: { read_only: true, tags: ["x"] },
      reject: ["a"],
      warn: [],
      require: [],
      mapping: [],
    }),
    putRules: vi.fn(),
    testRules: vi.fn(),
    health: vi
      .fn()
      .mockResolvedValue({
        stash: { state: "ok" },
        komga: { state: "ok" },
        db: "ok",
        mounts: [],
        sites: [],
      }),
    getConnections: vi
      .fn()
      .mockResolvedValue({ can_store: true, connections: [] }),
  };
}

// ── Setup / teardown ──────────────────────────────────────────────

let navSpy: ReturnType<typeof vi.fn>;
let api: ReturnType<typeof makeApi>;

beforeEach(() => {
  navSpy = vi.fn();
  hoisted.router = mockRouter(navSpy);
  api = makeApi();
  hoisted.api = api;
  mockMatchMedia(false);
});

afterEach(() => {
  cleanup();
  history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function makeDirty() {
  const input = await screen.findByLabelText("Add to Reject");
  fireEvent.input(input, { target: { value: "newtag" } });
  const form = input.closest("form");
  if (form) fireEvent.submit(form);
  await tick();
  await tick();
}

// ── Tests ─────────────────────────────────────────────────────────

describe("OptionsRulesGuard", () => {
  it("clean rules: clicking Library navigates, no prompt", async () => {
    render(Options, { props: { match: makeMatch() } });
    await tick();
    await tick();

    await screen.findByLabelText("Add to Reject");
    const libBtn = screen.getByRole("button", { name: "Library" });
    fireEvent.click(libBtn);
    await tick();

    expect(navSpy).toHaveBeenCalledWith("/options/library");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("dirty: clicking Library shows prompt; Stay keeps edits", async () => {
    render(Options, { props: { match: makeMatch() } });
    await tick();
    await makeDirty();

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(
      screen.getByRole("region", { name: "Unsaved changes" })
    ).toBeTruthy();

    const libBtn = screen.getByRole("button", { name: "Library" });
    fireEvent.click(libBtn);
    await tick();

    expect(
      screen.getByRole("alertdialog", { name: "Leave this page?" })
    ).toBeTruthy();
    expect(navSpy).not.toHaveBeenCalled();

    const stayBtn = screen.getByRole("button", { name: "Stay" });
    fireEvent.click(stayBtn);
    await tick();

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(
      screen.getByRole("region", { name: "Unsaved changes" })
    ).toBeTruthy();
    expect(screen.getByText("newtag")).toBeTruthy();
    expect(navSpy).not.toHaveBeenCalled();
  });

  it("dirty: Leave navigates and discards", async () => {
    render(Options, { props: { match: makeMatch() } });
    await tick();
    await makeDirty();

    const libBtn = screen.getByRole("button", { name: "Library" });
    fireEvent.click(libBtn);
    await tick();

    expect(
      screen.getByRole("alertdialog", { name: "Leave this page?" })
    ).toBeTruthy();
    expect(navSpy).not.toHaveBeenCalled();

    const leaveBtn = screen.getByRole("button", { name: "Leave" });
    fireEvent.click(leaveBtn);
    await tick();

    expect(navSpy).toHaveBeenCalledTimes(1);
    expect(navSpy).toHaveBeenCalledWith("/options/library");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("phone: dirty, Back to options shows prompt; Leave → /options", async () => {
    mockMatchMedia(true);
    render(Options, { props: { match: makeMatch() } });
    await tick();
    await makeDirty();

    const backBtn = screen.getByRole("button", {
      name: "Back to options",
    });
    fireEvent.click(backBtn);
    await tick();

    expect(
      screen.getByRole("alertdialog", { name: "Leave this page?" })
    ).toBeTruthy();
    expect(navSpy).not.toHaveBeenCalled();

    const leaveBtn = screen.getByRole("button", { name: "Leave" });
    fireEvent.click(leaveBtn);
    await tick();

    expect(navSpy).toHaveBeenCalledWith("/options");
  });

  it("popstate: dirty, back button shows prompt, URL restored", async () => {
    history.replaceState({}, "", "/options/rules");
    render(Options, { props: { match: makeMatch() } });
    await tick();
    await makeDirty();

    history.pushState({}, "", "/options/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await tick();

    expect(
      screen.getByRole("alertdialog", { name: "Leave this page?" })
    ).toBeTruthy();
    expect(location.pathname).toBe("/options/rules");

    const stayBtn = screen.getByRole("button", { name: "Stay" });
    fireEvent.click(stayBtn);
    await tick();

    expect(location.pathname).toBe("/options/rules");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("Rules section: no Status h2", async () => {
    render(Options, { props: { match: makeMatch() } });
    await tick();
    await tick();

    const h2s = document.querySelectorAll("h2");
    const hasStatus = Array.from(h2s).some((h) =>
      h.textContent?.includes("Status")
    );
    expect(hasStatus).toBe(false);
  });

  it("Library section: Status h2 after health resolves", async () => {
    render(Options, {
      props: {
        match: makeMatch({
          params: { section: "library" },
          path: "/options/library",
        }),
      },
    });
    await tick();

    await vi.waitFor(
      () => {
        const h2s = document.querySelectorAll("h2");
        expect(
          Array.from(h2s).some((h) => h.textContent?.includes("Status"))
        ).toBe(true);
      },
      { timeout: 2000 }
    );
  });
});
