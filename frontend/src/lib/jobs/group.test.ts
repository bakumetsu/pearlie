import { describe, it, expect } from "vitest";
import {
  groupJobs,
  activeCount,
  pollDelayMs,
  etaLabel,
  stateInfo,
  canRetry,
  canRemove,
  removeLabel,
  attentionText,
  needsFolderFix,
  routeFor,
  type Job,
} from "./group";

function mk(partial: Partial<Job>): Job {
  return {
    id: "id-1",
    state: "queued",
    created_at: "2025-01-01T00:00:00Z",
    ...partial,
  } as Job;
}

describe("groupJobs", () => {
  it("orders running before queued, running newest-first, queued oldest-first", () => {
    const r1 = mk({ id: "r1", state: "running", created_at: "2025-01-03T00:00:00Z" });
    const r2 = mk({ id: "r2", state: "running", created_at: "2025-01-01T00:00:00Z" });
    const q1 = mk({ id: "q1", state: "queued", created_at: "2025-01-05T00:00:00Z" });
    const q2 = mk({ id: "q2", state: "queued", created_at: "2025-01-02T00:00:00Z" });

    const { active } = groupJobs([q1, r2, r1, q2]);

    expect(active.map((j) => j.id)).toEqual(["r1", "r2", "q2", "q1"]);
  });

  it("collects failed and needs_click into attention, newest first", () => {
    const f1 = mk({ id: "f1", state: "failed", created_at: "2025-01-01T00:00:00Z" });
    const n1 = mk({ id: "n1", state: "needs_click", created_at: "2025-01-05T00:00:00Z" });
    const f2 = mk({ id: "f2", state: "failed", created_at: "2025-01-03T00:00:00Z" });

    const { attention } = groupJobs([f1, n1, f2]);

    expect(attention.map((j) => j.id)).toEqual(["n1", "f2", "f1"]);
  });

  it("caps done at 50", () => {
    const jobs: Job[] = [];
    for (let i = 0; i < 60; i++) {
      jobs.push(
        mk({
          id: `d${i}`,
          state: "done",
          created_at: `2025-01-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
          finished_at: `2025-01-${String(i + 1).padStart(2, "0")}T01:00:00Z`,
        }),
      );
    }

    const { done } = groupJobs(jobs);

    expect(done).toHaveLength(50);
    // newest finished_at first → d59 (day 60) is newest, but we keep the newest 50: d59..d10
    expect(done[0].id).toBe("d59");
    expect(done[49].id).toBe("d10");
  });

  it("does not mutate the input array", () => {
    const jobs = [
      mk({ id: "a", state: "queued", created_at: "2025-01-02T00:00:00Z" }),
      mk({ id: "b", state: "running", created_at: "2025-01-01T00:00:00Z" }),
      mk({ id: "c", state: "done", created_at: "2025-01-03T00:00:00Z" }),
    ];
    const original = jobs.map((j) => j.id);

    groupJobs(jobs);

    expect(jobs.map((j) => j.id)).toEqual(original);
  });
});

describe("activeCount", () => {
  it("counts running + queued", () => {
    const jobs = [
      mk({ state: "running" }),
      mk({ state: "queued" }),
      mk({ state: "queued" }),
      mk({ state: "done" }),
      mk({ state: "failed" }),
    ];
    expect(activeCount(jobs)).toBe(3);
  });
});

describe("pollDelayMs", () => {
  const activeJobs = [mk({ state: "running" })];
  const idleJobs = [mk({ state: "done" })];

  it("returns 2000 when active and visible", () => {
    expect(pollDelayMs(activeJobs, true)).toBe(2000);
  });

  it("returns 15000 when active but not visible", () => {
    expect(pollDelayMs(activeJobs, false)).toBe(15000);
  });

  it("returns 15000 when idle and visible", () => {
    expect(pollDelayMs(idleJobs, true)).toBe(15000);
  });

  it("returns 15000 when idle and not visible", () => {
    expect(pollDelayMs(idleJobs, false)).toBe(15000);
  });
});

describe("etaLabel", () => {
  it("returns null for running job", () => {
    expect(etaLabel(mk({ state: "running", eta_s: 5 }))).toBeNull();
  });

  it("returns null when eta_s is 0", () => {
    expect(etaLabel(mk({ state: "queued", eta_s: 0 }))).toBeNull();
  });

  it("returns null when eta_s is missing", () => {
    expect(etaLabel(mk({ state: "queued" }))).toBeNull();
  });

  it("returns formatted label for queued with eta_s 2.1", () => {
    expect(etaLabel(mk({ state: "queued", eta_s: 2.1 }))).toBe("waits 3 s");
  });
});

describe("stateInfo", () => {
  const cases: [Job["state"], string, string][] = [
    ["queued", "Queued", "clock"],
    ["running", "Running", "download"],
    ["done", "Done", "check"],
    ["failed", "Failed", "alert"],
    ["needs_click", "Needs a click", "alert"],
    ["skipped", "Skipped", "minus"],
  ];

  for (const [state, label, icon] of cases) {
    it(`maps ${state} → "${label}" / "${icon}"`, () => {
      expect(stateInfo(state)).toEqual({ label, icon });
    });
  }
});

describe("canRetry / canRemove / removeLabel", () => {
  it("canRetry true for failed and needs_click, false otherwise", () => {
    expect(canRetry(mk({ state: "failed" }))).toBe(true);
    expect(canRetry(mk({ state: "needs_click" }))).toBe(true);
    expect(canRetry(mk({ state: "queued" }))).toBe(false);
    expect(canRetry(mk({ state: "running" }))).toBe(false);
    expect(canRetry(mk({ state: "done" }))).toBe(false);
  });

  it("canRemove true for all states except running", () => {
    expect(canRemove(mk({ state: "running" }))).toBe(false);
    expect(canRemove(mk({ state: "queued" }))).toBe(true);
    expect(canRemove(mk({ state: "done" }))).toBe(true);
    expect(canRemove(mk({ state: "failed" }))).toBe(true);
    expect(canRemove(mk({ state: "needs_click" }))).toBe(true);
    expect(canRemove(mk({ state: "skipped" }))).toBe(true);
  });

  it("removeLabel is Cancel for queued, Remove otherwise", () => {
    expect(removeLabel(mk({ state: "queued" }))).toBe("Cancel");
    expect(removeLabel(mk({ state: "done" }))).toBe("Remove");
    expect(removeLabel(mk({ state: "failed" }))).toBe("Remove");
  });
});

describe("attentionText", () => {
  it("returns prompt for needs_click", () => {
    expect(attentionText(mk({ state: "needs_click" }))).toBe(
      "Open the site in your browser and solve the check",
    );
  });

  it("returns error message for failed with error", () => {
    expect(attentionText(mk({ state: "failed", error: "Timeout" }))).toBe("Timeout");
  });

  it("returns 'Failed' for failed without error", () => {
    expect(attentionText(mk({ state: "failed" }))).toBe("Failed");
  });

  it("returns empty string for other states", () => {
    expect(attentionText(mk({ state: "queued" }))).toBe("");
    expect(attentionText(mk({ state: "running" }))).toBe("");
  });
});

describe("routeFor", () => {
  const kinds: [string, string][] = [
    ["image", "images"],
    ["video", "videos"],
    ["series", "series"],
    ["book", "books"],
  ];

  for (const [kind, plural] of kinds) {
    it(`maps ref.kind "${kind}" → /item/${plural}/42`, () => {
      const job = mk({
        library_ref: { kind: kind as "image" | "video" | "series" | "book", id: "42" },
      });
      expect(routeFor(job)).toBe(`/item/${plural}/42`);
    });
  }

  it("returns null when library_ref is absent", () => {
    expect(routeFor(mk({}))).toBeNull();
  });
});


describe("needsFolderFix", () => {
  it("is true only for a failed job with the outside-library error", () => {
    const msg = "folder is not inside a Stash library path";
    expect(needsFolderFix(mk({ state: "failed", error: msg }))).toBe(true);
    expect(needsFolderFix(mk({ state: "failed", error: "Timeout" }))).toBe(false);
    expect(needsFolderFix(mk({ state: "failed" }))).toBe(false);
    expect(needsFolderFix(mk({ state: "queued", error: msg }))).toBe(false);
  });
});
