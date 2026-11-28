export type ThemeMode = "dark" | "light";

export interface Theme {
  id: string;
  label: string;
  mode: ThemeMode;
  /** Swatch colours for the Options radio card. The full values live in app.css `[data-theme="id"]`. */
  vars: { background: string; foreground: string; primary: string };
}

export const DEFAULT_THEME_ID = "dark";

// One more theme = one entry here + one `:root[data-theme="id"] .ui-root` block in app.css.
export const THEMES: readonly Theme[] = [
  { id: "dark", label: "Dark", mode: "dark", vars: { background: "#0b0b0d", foreground: "#ededf0", primary: "#9d9bff" } },
  { id: "light", label: "Light", mode: "light", vars: { background: "#fafafb", foreground: "#16161a", primary: "#5b58e6" } },
];

export function findTheme(id: string | null | undefined): Theme {
  return THEMES.find((t) => t.id === id) ?? THEMES.find((t) => t.id === DEFAULT_THEME_ID)!;
}
