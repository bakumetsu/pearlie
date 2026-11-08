import { getContext, setContext } from "svelte";
import type { Router } from "./router";

const KEY = Symbol("router");

export function setRouter(r: Router): void {
  setContext<Router>(KEY, r);
}

export function getRouter(): Router {
  const r = getContext<Router>(KEY);
  if (!r) throw new Error("router context missing");
  return r;
}
