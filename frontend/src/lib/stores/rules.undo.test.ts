import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createRules } from "./rules.svelte";
import type { Api } from "../api/client";
import type { Draft } from "../rules/draft";

const bodyFixture = {
  version: 3,
  base_list: { read_only: true, tags: ["x"] },
  reject: ["a"],
  warn: [],
  require: [],
  mapping: [],
};

const DEBOUNCE = 300;

function makeApi() {
  return {
    getRules: vi.fn(),
    putRules: vi.fn(),
    testRules: vi.fn(),
  } as unknown as Api;
}

describe("rules store undo (snapshot / restore)", () => {
  let api: ReturnType<typeof makeApi>;
  let store: ReturnType<typeof createRules>;

  beforeEach(() => {
    vi.useFakeTimers();
    api = makeApi();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function loaded() {
    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue(bodyFixture);
    store = createRules(api, { debounceMs: DEBOUNCE });
    await store.load();
    await vi.advanceTimersByTimeAsync(0);
    return store;
  }

  it("snapshot then discard then restore returns the dirty draft", async () => {
    const s = await loaded();
    s.addTo("reject", "b");
    expect(s.dirty).toBe(true);

    const snap = s.snapshot();
    expect(snap).not.toBeNull();

    s.discard();
    expect(s.dirty).toBe(false);

    s.restore(snap!);
    expect(s.dirty).toBe(true);
    expect((s.draft as { reject: string[] }).reject).toEqual(["a", "b"]);
  });

  it("importText then restore(prev) returns to the previous draft", async () => {
    const s = await loaded();
    s.addTo("reject", "b");
    const prev = s.snapshot();

    const importText = JSON.stringify({
      version: 3,
      reject: ["c"],
      warn: [],
      require: [],
      mapping: [],
    });
    const result = s.importText(importText);
    expect(result.ok).toBe(true);
    expect((s.draft as { reject: string[] }).reject).toEqual(["c"]);

    s.restore(prev!);
    expect((s.draft as { reject: string[] }).reject).toEqual(["a", "b"]);
  });

  it("restore when nothing loaded does not throw and leaves draft null", async () => {
    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue(bodyFixture);
    store = createRules(api, { debounceMs: DEBOUNCE });
    // load() is intentionally NOT called — draft and body are both null

    expect(() => {
      store.restore({ reject: ["x"], warn: [], require: [], mapping: [] } as Draft);
    }).not.toThrow();
    expect(store.draft).toBeNull();
  });
});
