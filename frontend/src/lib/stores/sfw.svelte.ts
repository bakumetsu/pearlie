import { resetReveals } from "./sfw-reveal";

interface SfwStore {
  readonly on: boolean;
  /** Called after toggle() so the options store can save the change; set() is silent. */
  onChange: ((on: boolean) => void) | null;
  toggle(): void;
  set(on: boolean): void;
}

export function createSfw(root: HTMLElement = document.documentElement): SfwStore {
  let state = $state(false);

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
      store.onChange?.(state);
    },
    set(on: boolean): void {
      state = on;
      apply();
    },
  };
  return store;
}

export const sfw = typeof document !== "undefined" ? createSfw() : null;
