// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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


describe("Rules file import", () => {
  it("catches a read failure and shows an error when the file cannot be read", async () => {
    const { container } = render(Options, { props: { match: makeMatch() } });
    await screen.findByLabelText("Add to Reject");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["{}"], "r.json", { type: "application/json" });
    file.text = () => Promise.reject(new Error("read failed"));
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    fireEvent.change(input);
    await new Promise((r) => setTimeout(r, 20));
    expect((await screen.findByRole("alert")).textContent).toContain("Could not read");
  });
});
