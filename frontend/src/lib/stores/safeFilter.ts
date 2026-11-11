import type { LibraryItem, WebItem } from "../api/client";
import { sfw } from "./sfw.svelte";
import { options } from "./options.svelte";

/** Safe mode drops warn-list posts unless "Allow blurred tags" is on; then they stay, blurred. */
export function isHiddenInSafeMode(item: LibraryItem | WebItem): boolean {
  return item.blur != null && !!sfw?.on && !(options.values?.allow_blurred_tags ?? false);
}

export function visibleInSafeMode<T extends LibraryItem | WebItem>(items: readonly T[]): T[] {
  return items.filter((i) => !isHiddenInSafeMode(i));
}
