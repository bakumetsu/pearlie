import type { LibraryItem } from "../api/client";
import { gridFor } from "../stores/shared.svelte";
import type { Loader } from "../stores/grid.svelte";

type VideoGrid = Pick<ReturnType<typeof gridFor>, "seed">;

// A video opened from a row queues that row's items; later pages come from the row's See all list.
export function seedVideoQueue(
  listKey: string,
  items: LibraryItem[],
  loader: Loader<LibraryItem>,
  meta: { total?: number | null; pageSize?: number | null; hasNext: boolean },
  grid: VideoGrid = gridFor("videos"),
): void {
  const videos = items.filter((i) => i.kind === "video");
  grid.seed(listKey, videos, loader as Loader<LibraryItem | never>, meta);
}
