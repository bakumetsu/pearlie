import { DEFAULT_THEME_ID, THEMES, findTheme, type Theme } from "./themes";

export const THEME_KEY = "pearlie.theme";

type ThemeStorage = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): ThemeStorage | undefined {
  try {
    return typeof localStorage !== "undefined" ? localStorage : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Applies a theme to the root element (data-theme, data-mode) before first paint.
 * The choice is stored in this browser only.
 */
export function createTheme(
  root: HTMLElement = document.documentElement,
  storage: ThemeStorage | undefined = defaultStorage(),
) {
  let current: Theme = findTheme(DEFAULT_THEME_ID);

  const apply = (t: Theme): void => {
    current = t;
    root.dataset.theme = t.id;
    root.dataset.mode = t.mode;
  };

  const read = (): string | null => {
    try {
      return storage?.getItem(THEME_KEY) ?? null;
    } catch {
      return null;
    }
  };

  apply(findTheme(read()));

  return {
    get current(): Theme {
      return current;
    },
    list: THEMES,
    set(id: string): void {
      apply(findTheme(id));
      try {
        storage?.setItem(THEME_KEY, current.id);
      } catch { /* storage blocked: the theme still applies for this page */ }
    },
  };
}

export const theme = createTheme();
