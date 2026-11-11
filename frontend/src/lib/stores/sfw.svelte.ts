import { resetReveals } from "./sfw-reveal";

interface SfwStore {
  readonly on: boolean;
  /** Called after toggle() so the options store can save the change; set() is silent. */
  onChange: ((on: boolean) => void) | null;
  toggle(): void;
  set(on: boolean): void;
}

const HINT_KEY = "pearlie.sfw.hint";

type HintStorage = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): HintStorage | undefined {
  try {
    return typeof localStorage !== "undefined" ? localStorage : undefined;
  } catch {
    return undefined;
  }
}

export function createSfw(
  root: HTMLElement = document.documentElement,
  storage: HintStorage | undefined = defaultStorage(),
): SfwStore {
  // Last-known value per browser: fail closed until the server value arrives
  const readHint = (): boolean => {
    try {
      return storage?.getItem(HINT_KEY) === "1";
    } catch {
      return false;
    }
  };
  const writeHint = (): void => {
    try {
      storage?.setItem(HINT_KEY, state ? "1" : "0");
    } catch { /* storage blocked: behave as without a hint */ }
  };

  let state = $state(readHint());

  const apply = (): void => {
    if (state) {
      root.dataset.sfw = "on";
    } else {
      delete root.dataset.sfw;
    }
    resetReveals(root);
  };

  apply();

  const store: SfwStore = {
    get on(): boolean {
      return state;
    },
    onChange: null,
    toggle(): void {
      state = !state;
      apply();
      writeHint();
      store.onChange?.(state);
    },
    set(on: boolean): void {
      state = on;
      apply();
      writeHint();
    },
  };
  return store;
}

export const sfw = typeof document !== "undefined" ? createSfw() : null;
