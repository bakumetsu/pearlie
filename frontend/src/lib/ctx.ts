import { getContext, setContext } from "svelte";
import type { Router } from "./router";
import type { Jobs } from "./stores/jobs.svelte";

const JOBS_KEY = Symbol("jobs");

export function setJobs(j: Jobs): void {
  setContext<Jobs>(JOBS_KEY, j);
}

export function getJobs(): Jobs {
  const j = getContext<Jobs>(JOBS_KEY);
  if (!j) throw new Error("jobs context missing");
  return j;
}

const KEY = Symbol("router");

export function setRouter(r: Router): void {
  setContext<Router>(KEY, r);
}

export function getRouter(): Router {
  const r = getContext<Router>(KEY);
  if (!r) throw new Error("router context missing");
  return r;
}
