interface RailStore {
  readonly collapsed: boolean;
  /** Rail width in px (the stored choice, also while collapsed). */
  readonly width: number;
  /** Width the layout uses: 0 while collapsed. */
  readonly px: number;
  toggle(): void;
  setWidth(px: number): void;
  resetWidth(): void;
}

const KEY = "pearlie.rail.collapsed";
const WIDTH_KEY = "pearlie.rail.width";
export const RAIL_MIN = 72;
export const RAIL_MAX = 240;
export const RAIL_DEFAULT = 72;

function clampWidth(px: number): number {
  if (!Number.isFinite(px)) return RAIL_DEFAULT;
  return Math.min(RAIL_MAX, Math.max(RAIL_MIN, Math.round(px)));
}

type RailStorage = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): RailStorage | undefined {
  try {
    return typeof localStorage !== "undefined" ? localStorage : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Desktop rail collapse and width (72-240 px), remembered per device.
 * Sets data-rail="hidden" on root (tokens.css sets --rail-w to 0) and an inline --rail-w while shown and not default.
 */
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
  const readWidth = (): number => {
    try {
      const raw = storage?.getItem(WIDTH_KEY);
      return raw == null ? RAIL_DEFAULT : clampWidth(Number(raw));
    } catch {
      return RAIL_DEFAULT;
    }
  };
  const write = (): void => {
    try {
      storage?.setItem(KEY, state ? "1" : "0");
    } catch { /* storage blocked: the choice lasts until reload */ }
  };
  const writeWidth = (): void => {
    try {
      storage?.setItem(WIDTH_KEY, String(w));
    } catch { /* storage blocked: the choice lasts until reload */ }
  };

  let state = $state(read());
  let w = $state(readWidth());

  const apply = (): void => {
    if (state) {
      root.dataset.rail = "hidden";
    } else {
      delete root.dataset.rail;
    }
    if (state || w === RAIL_DEFAULT) {
      root.style.removeProperty("--rail-w");
    } else {
      root.style.setProperty("--rail-w", `${w}px`);
    }
  };

  apply();

  return {
    get collapsed(): boolean {
      return state;
    },
    get width(): number {
      return w;
    },
    get px(): number {
      return state ? 0 : w;
    },
    setWidth(px: number): void {
      w = clampWidth(px);
      apply();
      writeWidth();
    },
    resetWidth(): void {
      w = RAIL_DEFAULT;
      apply();
      writeWidth();
    },
    toggle(): void {
      state = !state;
      apply();
      write();
    },
  };
}

export const rail = typeof document !== "undefined" ? createRail() : null;
