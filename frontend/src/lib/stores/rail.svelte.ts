interface RailStore {
  readonly collapsed: boolean;
  toggle(): void;
}

const KEY = "pearlie.rail.collapsed";

type RailStorage = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): RailStorage | undefined {
  try {
    return typeof localStorage !== "undefined" ? localStorage : undefined;
  } catch {
    return undefined;
  }
}

/** Desktop rail collapse, remembered per device. Sets data-rail="slim" on root; tokens.css narrows --rail-w. */
export function createRail(
  root: HTMLElement = document.documentElement,
  storage: RailStorage | undefined = defaultStorage(),
): RailStore {
  const read = (): boolean => {
    try {
      return storage?.getItem(KEY) === "1";
    } catch {
      return false;
    }
  };
  const write = (): void => {
    try {
      storage?.setItem(KEY, state ? "1" : "0");
    } catch { /* storage blocked: the choice lasts until reload */ }
  };

  let state = $state(read());

  const apply = (): void => {
    if (state) {
      root.dataset.rail = "slim";
    } else {
      delete root.dataset.rail;
    }
  };

  apply();

  return {
    get collapsed(): boolean {
      return state;
    },
    toggle(): void {
      state = !state;
      apply();
      write();
    },
  };
}

export const rail = typeof document !== "undefined" ? createRail() : null;
