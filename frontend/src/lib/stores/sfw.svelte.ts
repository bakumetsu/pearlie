import { resetReveals } from "./sfw-reveal";

export const SFW_KEY = "pearlie.sfw";

export function loadSfw(storage: Storage = localStorage): boolean {
  try {
    return storage.getItem(SFW_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveSfw(on: boolean, storage: Storage = localStorage): void {
  try {
    storage.setItem(SFW_KEY, on ? "1" : "0");
  } catch {
    // ignore
  }
}

interface SfwStore {
  readonly on: boolean;
  toggle(): void;
  set(on: boolean): void;
}

export function createSfw(
  storage: Storage = localStorage,
  root: HTMLElement = document.documentElement,
): SfwStore {
  let state = $state(loadSfw(storage));

  const apply = (): void => {
    if (state) {
      root.dataset.sfw = "on";
    } else {
      delete root.dataset.sfw;
    }
    saveSfw(state, storage);
    resetReveals(root);
  };

  apply();

  return {
    get on(): boolean {
      return state;
    },
    toggle(): void {
      state = !state;
      apply();
    },
    set(on: boolean): void {
      state = on;
      apply();
    },
  };
}

export const sfw = typeof document !== "undefined" ? createSfw() : null;
