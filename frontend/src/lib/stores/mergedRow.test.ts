// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { Api, MergedRow, MergedSite, WebItem } from "../api/client";
import { createMergedRow, clearMergedAnswers, POLL_MS, POLL_MAX } from "./mergedRow.svelte";

const site = (id: MergedSite["id"], state: MergedSite["state"], message?: string): MergedSite => ({ id, title: id, state, count: state === "ok" ? 1 : 0, message });
const item = (source: string, n: number) => ({ source, post_id: String(n) }) as unknown as WebItem;
const row = (over: Partial<MergedRow>): MergedRow => ({ items: [], sites: [], hidden: 0, pending: false, ...over });

function fakeApi(answers: MergedRow[] | (() => Promise<MergedRow>)) {
  let i = 0;
  const calls: { have?: string[]; signal?: AbortSignal }[] = [];
  const mergedRow = vi.fn((p: { have?: string[] }, signal?: AbortSignal) => {
    calls.push({ have: p.have, signal });
    if (typeof answers === "function") return answers();
    return Promise.resolve(answers[Math.min(i++, answers.length - 1)]);
  });
  return { api: { mergedRow } as unknown as Api, calls, mergedRow };
}

beforeEach(() => {
  vi.useFakeTimers();
  clearMergedAnswers();
});
afterEach(() => vi.useRealTimers());

describe("createMergedRow", () => {
  it("loads once and keeps a complete answer for 10 minutes", async () => {
    const { api, mergedRow } = fakeApi([row({ items: [item("danbooru", 1)], sites: [site("danbooru", "ok"), site("gelbooru", "ok")] })]);
    const m = createMergedRow(api);
    m.load();
    expect(m.status).toBe("loading");
    await vi.advanceTimersByTimeAsync(0);
    expect(m.status).toBe("done");
    expect(m.items).toHaveLength(1);
    m.load();
    expect(mergedRow).toHaveBeenCalledTimes(1);
    expect(m.status).toBe("done");
  });

  it("polls every 3 s while pending, sends have, appends the late site and stops", async () => {
    const first = row({ items: [item("danbooru", 1)], sites: [site("danbooru", "ok"), site("rule34", "pending")], pending: true });
    const done = row({ items: [item("danbooru", 1), item("rule34", 2)], sites: [site("danbooru", "ok"), site("rule34", "ok")] });
    const { api, calls } = fakeApi([first, done]);
    const m = createMergedRow(api);
    m.load();
    await vi.advanceTimersByTimeAsync(0);
    expect(m.pending).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].have).toEqual([]);
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(calls).toHaveLength(2);
    expect(calls[1].have).toEqual(["danbooru"]);
    expect(m.items.map((i) => i.source)).toEqual(["danbooru", "rule34"]);
    expect(m.pending).toBe(false);
    await vi.advanceTimersByTimeAsync(POLL_MS * 3);
    expect(calls).toHaveLength(2);
  });

  it("polls at most POLL_MAX times and never keeps a partial answer", async () => {
    const pend = row({ items: [item("danbooru", 1)], sites: [site("danbooru", "ok"), site("rule34", "pending")], pending: true });
    const { api, mergedRow } = fakeApi([pend]);
    const m = createMergedRow(api);
    m.load();
    await vi.advanceTimersByTimeAsync(POLL_MS * (POLL_MAX + 3));
    expect(mergedRow).toHaveBeenCalledTimes(1 + POLL_MAX);
    m.load();
    expect(mergedRow).toHaveBeenCalledTimes(2 + POLL_MAX);
  });

  it("abort stops the request and the poll timer, and a late answer is ignored", async () => {
    let resolve!: (r: MergedRow) => void;
    const { api, calls } = fakeApi(() => new Promise<MergedRow>((r) => (resolve = r)));
    const m = createMergedRow(api);
    m.load();
    m.abort();
    expect(calls[0].signal!.aborted).toBe(true);
    expect(m.status).toBe("idle");
    resolve(row({ items: [item("danbooru", 1)], sites: [site("danbooru", "ok")] }));
    await vi.advanceTimersByTimeAsync(0);
    expect(m.items).toHaveLength(0);

    const pend = row({ sites: [site("danbooru", "ok"), site("rule34", "pending")], pending: true });
    const f = fakeApi([pend]);
    const m2 = createMergedRow(f.api);
    m2.load();
    await vi.advanceTimersByTimeAsync(0);
    m2.abort();
    await vi.advanceTimersByTimeAsync(POLL_MS * 2);
    expect(f.mergedRow).toHaveBeenCalledTimes(1);
  });

  it("shows the error state with Retry only when every site failed", async () => {
    const bad = row({ sites: [site("danbooru", "error", "boom"), site("gelbooru", "rate_limited")] });
    const { api, mergedRow } = fakeApi([bad]);
    const m = createMergedRow(api);
    m.load();
    await vi.advanceTimersByTimeAsync(0);
    expect(m.status).toBe("error");
    expect(m.error).toBe("boom");
    m.retry();
    expect(mergedRow).toHaveBeenCalledTimes(2);
  });

  it("a partial answer with one failed site is done, with no error", async () => {
    const { api } = fakeApi([row({ items: [item("danbooru", 1)], sites: [site("danbooru", "ok"), site("gelbooru", "error")] })]);
    const m = createMergedRow(api);
    m.load();
    await vi.advanceTimersByTimeAsync(0);
    expect(m.status).toBe("done");
    expect(m.error).toBeNull();
  });
});
