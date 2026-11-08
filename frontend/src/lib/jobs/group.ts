import type { components } from "../api/schema.gen";
export type Job = components["schemas"]["Job"];

export type JobGroups = {
  active: Job[];
  attention: Job[];
  done: Job[];
};

export function groupJobs(jobs: Job[]): JobGroups {
  const running = jobs
    .filter((j) => j.state === "running")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  const queued = jobs
    .filter((j) => j.state === "queued")
    .sort((a, b) => a.created_at.localeCompare(b.created_at));

  const attention = jobs
    .filter((j) => j.state === "failed" || j.state === "needs_click")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  const done = jobs
    .filter((j) => j.state === "done" || j.state === "skipped")
    .sort(
      (a, b) =>
        (b.finished_at ?? b.created_at).localeCompare(
          a.finished_at ?? a.created_at,
        ),
    )
    .slice(0, 50);

  return {
    active: [...running, ...queued],
    attention,
    done,
  };
}

export function activeCount(jobs: Job[]): number {
  return jobs.filter(
    (j) => j.state === "running" || j.state === "queued",
  ).length;
}

export function pollDelayMs(jobs: Job[], visible: boolean): number {
  if (
    visible &&
    jobs.some((j) => j.state === "running" || j.state === "queued")
  ) {
    return 2000;
  }
  return 15000;
}

export function etaLabel(job: Job): string | null {
  if (job.state === "queued" && job.eta_s != null && job.eta_s > 0) {
    return `waits ${Math.ceil(job.eta_s)} s`;
  }
  return null;
}

export function stateInfo(
  state: Job["state"],
): { label: string; icon: string } {
  const map: Record<Job["state"], { label: string; icon: string }> = {
    queued: { label: "Queued", icon: "clock" },
    running: { label: "Running", icon: "download" },
    done: { label: "Done", icon: "check" },
    failed: { label: "Failed", icon: "alert" },
    needs_click: { label: "Needs a click", icon: "alert" },
    skipped: { label: "Skipped", icon: "minus" },
  };
  return map[state];
}

export function canRetry(job: Job): boolean {
  return job.state === "failed" || job.state === "needs_click";
}

export function canRemove(job: Job): boolean {
  return job.state !== "running";
}

export function removeLabel(job: Job): string {
  return job.state === "queued" ? "Cancel" : "Remove";
}

export function attentionText(job: Job): string {
  if (job.state === "needs_click") {
    return "Open the site in your browser and solve the check";
  }
  if (job.state === "failed") {
    return job.error ?? "Failed";
  }
  return "";
}

export function routeFor(job: Job): string | null {
  const ref = job.library_ref;
  if (!ref) return null;
  const pluralMap: Record<string, string> = {
    image: "images",
    video: "videos",
    series: "series",
    book: "books",
  };
  const plural = pluralMap[ref.kind];
  if (!plural) return null;
  return `/item/${plural}/${ref.id}`;
}

