import type { LibraryItem, WebItem } from "../api/client";
import { gridFor } from "../stores/shared.svelte";
import type { Loader } from "../stores/grid.svelte";

type VideoGrid = Pick<ReturnType<typeof gridFor>, "seed">;

// A video opened from a row queues that row's items; later pages come from the row's See all list.
export function seedVideoQueue(
  listKey: string,
  items: (LibraryItem | WebItem)[],
  loader: Loader<LibraryItem | WebItem>,
  meta: { total?: number | null; pageSize?: number | null; hasNext: boolean },
  grid: VideoGrid = gridFor("videos"),
): void {
  const videos = items.filter((i) => !("post_id" in i) && i.kind === "video");
  grid.seed(listKey, videos, loader, meta);
}
