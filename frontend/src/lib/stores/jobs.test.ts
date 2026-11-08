import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { createJobs } from "./jobs.svelte";
import type { Api } from "../api/client";
import { ApiError } from "../api/client";
import type { Job } from "../jobs/group";
import { toasts } from "./toasts.svelte";

function mk(partial: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    source: "danbooru",
    post_id: "12345",
    title: "Test Post",
    thumb_url: "https://example.com/thumb.jpg",
    target: "stash",
    state: "queued",
    progress: 0,
    created_at: "2026-11-08T10:00:00Z",
    ...partial,
  };
}

function makeApi() {
  return {
    jobs: vi.fn(),
    retryJob: vi.fn(),
    removeJob: vi.fn(),
  } as unknown as Api & { jobs: Mock; retryJob: Mock; removeJob: Mock };
}

describe("jobs store", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    while (toasts.current) toasts.dismiss();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("refresh fills items and groups", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [mk(), mk({ id: "job-2", state: "done" })] });
    const store = createJobs(api);

    await store.refresh();

    expect(api.jobs).toHaveBeenCalledWith({}, expect.any(AbortSignal));
    expect(store.items).toHaveLength(2);
    expect(store.loaded).toBe(true);
    expect(store.offline).toBe(false);
    expect(store.groups).toBeDefined();
  });

  it("failure keeps old list and sets offline; success clears it", async () => {
    const api = makeApi();
    const store = createJobs(api);

    api.jobs.mockResolvedValueOnce({ items: [mk()] });
    await store.refresh();
    expect(store.items).toHaveLength(1);
    expect(store.offline).toBe(false);

    api.jobs.mockRejectedValueOnce(new Error("network error"));
    await store.refresh();
    expect(store.items).toHaveLength(1);
    expect(store.offline).toBe(true);
    expect(store.loaded).toBe(true);

    api.jobs.mockResolvedValueOnce({ items: [mk({ id: "job-2" })] });
    await store.refresh();
    expect(store.items).toHaveLength(1);
    expect(store.offline).toBe(false);
  });

  it("start polls every 2000ms while a job is running", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [mk({ state: "running" })] });
    const store = createJobs(api, { visible: () => true });

    store.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(2);

    store.stop();
  });

  it("start polls every 15000ms when no job is running", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [] });
    const store = createJobs(api, { visible: () => true });

    store.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(15000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(2);

    store.stop();
  });

  it("hidden tab uses 15000ms delay", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [mk({ state: "running" })] });
    const store = createJobs(api, { visible: () => false });

    store.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(15000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(2);

    store.stop();
  });

  it("stop halts polling", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [mk({ state: "running" })] });
    const store = createJobs(api, { visible: () => true });

    store.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.jobs).toHaveBeenCalledTimes(1);

    store.stop();
    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(15000);
    expect(api.jobs).toHaveBeenCalledTimes(1);
  });

  it("badge counts running + queued", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({
      items: [mk({ id: "a", state: "running" }), mk({ id: "b", state: "queued" }), mk({ id: "c", state: "done" })],
    });
    const store = createJobs(api);

    await store.refresh();
    expect(store.badge).toBe(2);
  });

  it("retry replaces the job", async () => {
    const api = makeApi();
    const original = mk({ id: "job-1", state: "queued" });
    const retried = mk({ id: "job-1", state: "running", progress: 50 });
    api.jobs.mockResolvedValue({ items: [original] });
    api.retryJob.mockResolvedValue(retried);

    const store = createJobs(api);
    await store.refresh();

    await store.retry("job-1");

    expect(api.retryJob).toHaveBeenCalledWith("job-1");
    expect(store.items[0]).toEqual(retried);
  });

  it("remove drops the job", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [mk({ id: "a" }), mk({ id: "b" })] });
    api.removeJob.mockResolvedValue(undefined);

    const store = createJobs(api);
    await store.refresh();

    await store.remove("a");

    expect(api.removeJob).toHaveBeenCalledWith("a");
    expect(store.items).toHaveLength(1);
    expect(store.items[0].id).toBe("b");
  });

  it("remove failure leaves the job and pushes an error toast", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({ items: [mk({ id: "a" })] });
    api.removeJob.mockRejectedValue(new ApiError(409, "conflict", "Job is running"));

    const store = createJobs(api);
    await store.refresh();

    await store.remove("a");

    expect(store.items).toHaveLength(1);
    expect(toasts.current?.kind).toBe("error");
  });

  it("clearFinished removes only done/skipped jobs and shows one info toast", async () => {
    const api = makeApi();
    api.jobs.mockResolvedValue({
      items: [mk({ id: "a", state: "done" }), mk({ id: "b", state: "skipped" }), mk({ id: "c", state: "running" })],
    });
    api.removeJob.mockResolvedValue(undefined);

    const store = createJobs(api);
    await store.refresh();

    await store.clearFinished();

    expect(api.removeJob).toHaveBeenCalledTimes(2);
    expect(api.removeJob).toHaveBeenCalledWith("a");
    expect(api.removeJob).toHaveBeenCalledWith("b");
    expect(store.items).toHaveLength(1);
    expect(store.items[0].id).toBe("c");
    expect(toasts.current?.kind).toBe("info");
    expect(toasts.current?.message).toBe("Cleared 2 finished");
  });
});

