// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import { screen, fireEvent } from "@testing-library/dom";
import Options from "./Options.svelte";
import type { Router, Match } from "../lib/router";
import { toasts } from "../lib/stores/toasts.svelte";

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
        stump: { state: "ok" },
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
  toasts.dismiss();
});

afterEach(() => {
  cleanup();
  history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── Helper: make the draft dirty via the Reject input ─────────────

async function makeDirty(): Promise<void> {
  const rejectInput = await screen.findByLabelText("Add to Reject");
  fireEvent.input(rejectInput, { target: { value: "mytag" } });
  const form = rejectInput.closest("form")!;
  const addBtn = form.querySelector<HTMLButtonElement>("button[type='submit']")!;
  fireEvent.click(addBtn);
  await screen.findByRole("region", { name: "Unsaved changes" });
}

describe("Rules undo toasts", () => {
  it("pushes an 'undo' toast 'Changes discarded' on Discard; Undo restores the unsaved-changes bar", async () => {
    render(Options, { props: { match: makeMatch() } });

    await makeDirty();

    // Click Discard
    const discardBtn = screen.getByRole("button", { name: "Discard" });
    fireEvent.click(discardBtn);

    // Toast is present and correct
    expect(toasts.current?.message).toBe("Changes discarded");
    expect(toasts.current?.kind).toBe("undo");

    // Undo restores the previous (dirty) state → bar reappears
    toasts.runAction();
    await screen.findByRole("region", { name: "Unsaved changes" });
  });

  it("pushes an 'undo' toast 'Rules imported' on successful import; Undo restores the unsaved-changes bar", async () => {
    const { container } = render(Options, { props: { match: makeMatch() } });

    // Make dirty so the pre-import snapshot is dirty
    await makeDirty();

    // Trigger a successful file import
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const json = JSON.stringify({
      version: 3,
      base_list: { read_only: true, tags: ["y"] },
      reject: ["b"],
      warn: [],
      require: [],
      mapping: [],
    });
    const file = new File([""], "rules.json", { type: "application/json" });
    file.text = () => Promise.resolve(json);
    Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
    fireEvent.change(fileInput);

    // Wait for the async file.text() → importText() → toasts.push chain
    await new Promise((r) => setTimeout(r, 20));

    // Toast is present and correct
    expect(toasts.current?.message).toBe("Rules imported");
    expect(toasts.current?.kind).toBe("undo");

    // Undo restores the pre-import (dirty) snapshot → bar reappears
    toasts.runAction();
    await screen.findByRole("region", { name: "Unsaved changes" });
  });
});
