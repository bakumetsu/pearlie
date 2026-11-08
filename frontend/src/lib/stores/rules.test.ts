import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createRules } from "./rules.svelte";
import type { Api } from "../api/client";
import { ApiError } from "../api/client";

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
    health: vi.fn(),
    testRules: vi.fn(),
  } as unknown as Api;
}

describe("rules store", () => {
  let api: ReturnType<typeof makeApi>;
  let store: ReturnType<typeof createRules>;

  beforeEach(() => {
    vi.useFakeTimers();
    api = makeApi();
    (api.health as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });
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

  it("load fills draft and starts clean", async () => {
    const s = await loaded();
    expect(s.status).toBe("ready");
    expect(s.body).toEqual(bodyFixture);
    expect(s.draft).not.toBeNull();
    expect(s.dirty).toBe(false);
    expect(s.summary).toBe("No changes");
  });

  it("addTo makes dirty and summary reads +1 reject", async () => {
    const s = await loaded();
    s.addTo("reject", "b");
    expect(s.dirty).toBe(true);
    expect(s.summary).toBe("+1 reject");
  });

  it("discard restores the draft", async () => {
    const s = await loaded();
    s.addTo("reject", "b");
    expect(s.dirty).toBe(true);
    s.discard();
    expect(s.dirty).toBe(false);
    expect(s.summary).toBe("No changes");
  });

  it("save sends toPut with version 3 and adopts the response", async () => {
    const saved = { ...bodyFixture, reject: ["a", "b"], version: 4 };
    const s = await loaded();
    (api.putRules as ReturnType<typeof vi.fn>).mockResolvedValue(saved);

    s.addTo("reject", "b");
    const ok = await s.save();

    expect(ok).toBe(true);
    expect(api.putRules).toHaveBeenCalledWith(
      expect.objectContaining({ version: 3 }),
    );
    expect(s.body).toEqual(saved);
    expect(s.dirty).toBe(false);
  });

  it("409 stale_version sets conflict and keeps the draft", async () => {
    const s = await loaded();
    (api.putRules as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(409, "stale_version", "stale"),
    );

    s.addTo("reject", "b");
    const draftBefore = s.draft;
    const ok = await s.save();

    expect(ok).toBe(false);
    expect(s.conflict).toBe(true);
    expect(s.draft).toEqual(draftBefore);
  });

  it("reload clears the draft", async () => {
    const s = await loaded();
    s.addTo("reject", "b");
    expect(s.dirty).toBe(true);

    await s.reload();
    await vi.advanceTimersByTimeAsync(0);

    expect(s.dirty).toBe(false);
    expect(s.summary).toBe("No changes");
  });

  it("importText ok replaces the draft", async () => {
    const s = await loaded();
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
  });

  it("importText bad JSON returns error and keeps the draft", async () => {
    const s = await loaded();
    const draftBefore = s.draft;

    const result = s.importText("not json{");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBeTruthy();
    }
    expect(s.draft).toEqual(draftBefore);
  });

  it("exportText has no base_list", async () => {
    const s = await loaded();
    const text = s.exportText();
    expect(text).not.toBeNull();
    const parsed = JSON.parse(text as string);
    expect(parsed).not.toHaveProperty("base_list");
  });

  it("tester debounces: two quick calls produce one testRules with last tags", async () => {
    const s = await loaded();
    (api.testRules as ReturnType<typeof vi.fn>).mockResolvedValue({
      matches: [],
    });

    s.setTesterTags(["alpha"]);
    s.setTesterTags(["beta"]);
    vi.advanceTimersByTime(DEBOUNCE);
    await vi.advanceTimersByTimeAsync(0);

    expect(api.testRules).toHaveBeenCalledTimes(1);
    expect(api.testRules).toHaveBeenCalledWith(
      ["beta"],
      expect.any(AbortSignal),
    );
  });

  it("tester empty tags clear the result", async () => {
    const s = await loaded();
    (api.testRules as ReturnType<typeof vi.fn>).mockResolvedValue({
      matches: [{ tag: "x" }],
    });

    s.setTesterTags(["x"]);
    vi.advanceTimersByTime(DEBOUNCE);
    await vi.advanceTimersByTimeAsync(0);
    expect(s.tester.result).not.toBeNull();

    s.setTesterTags([]);
    expect(s.tester.result).toBeNull();
    expect(s.tester.loading).toBe(false);
  });

  it("health failure sets healthError", async () => {
    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue(bodyFixture);
    (api.health as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("down"),
    );

    const s = createRules(api, { debounceMs: DEBOUNCE });
    await s.load();
    await vi.advanceTimersByTimeAsync(0);

    expect(s.healthError).toBe(true);
    expect(s.health).toBeNull();
  });
});

