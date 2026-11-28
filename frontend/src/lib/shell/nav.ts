import type { IconName } from "$lib/components/Icon.svelte";

/** Same six tabs, names and paths as Nav.svelte:13-20. */
export const TABS: readonly { name: string; label: string; icon: IconName; path: string }[] = [
  { name: "discover", label: "Discover", icon: "search", path: "/" },
  { name: "home", label: "Home", icon: "home", path: "/home" },
  { name: "library", label: "Library", icon: "library", path: "/library" },
  { name: "queue", label: "Queue", icon: "queue", path: "/queue" },
  { name: "trash", label: "Trash", icon: "trash", path: "/trash" },
  { name: "options", label: "Options", icon: "wrench", path: "/options" },
];

/** Same rule as Nav.svelte:50-55: library_* routes keep the Library tab lit. */
export function isActive(name: string, current: string): boolean {
  if (name === "library") return current === "library" || current.startsWith("library_");
  return current === name;
}

/** Routes that draw their own full-screen view: the bars hide (Reader). */
export function hidesBars(current: string): boolean {
  return current === "read" || current === "read-web";
}

/** Pages below a tab: the phone top bar shows a back arrow. */
export function isDeep(current: string): boolean {
  return current === "item" || current === "seeall" || current === "web-book" || current.startsWith("library_");
}

export function titleFor(current: string): string {
  const tab = TABS.find((t) => isActive(t.name, current));
  if (tab) return tab.label;
  if (current === "item") return "Item";
  if (current === "seeall") return "See all";
  if (current === "web-book") return "Book";
  return "Pearlie";
}

/** Build-time flag read; a function so tests can pass a value. */
export function shellEnabled(value: string | undefined = import.meta.env.VITE_UI_SHELL): boolean {
  return value === "1" || value === "true";
}
