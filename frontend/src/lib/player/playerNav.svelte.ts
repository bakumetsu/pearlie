// player prev/next over the see-all list: stage navigates by route, mini swaps in place
import { canStep, stepInList } from "../item/listNav";
import type { ListGrid } from "../item/listNav";
import { itemHref } from "../item/kinds";
import type { LibraryItemDetail } from "../api/client";
import type { PlayerNav, PlayerItem } from "./player.svelte";

export function toPlayerItem(d: LibraryItemDetail): PlayerItem | null {
  if (d.kind !== "video" || !d.stream_url) return null;
  return {
    id: d.id,
    title: d.title,
    streamUrl: d.stream_url,
    posterUrl: d.thumb_url,
    fallbacks: d.fallback_streams ?? [],
    href: itemHref(d),
  };
}

export function createPlayerNav(deps: {
  player: { item: PlayerItem | null; mode: string; swap(i: PlayerItem): void };
  grid: ListGrid;
  getDetail(kind: "videos", id: string): Promise<LibraryItemDetail>;
  navigate(href: string): void;
  notify(message: string): void;
}): PlayerNav {
  const { player, grid, getDetail, navigate, notify } = deps;
  let blocked = $state<Record<string, true>>({});

  function keyOf(): string | null {
    const item = player.item;
    return item ? "video:" + item.id : null;
  }

  function opts(): { kind: "video"; cross: boolean } {
    return player.mode === "stage"
      ? { kind: "video", cross: true }
      : { kind: "video", cross: false };
  }

  function blockKey(dir: 1 | -1, k: string): string {
    return dir + ":" + k + ":" + (player.mode === "stage" ? "stage" : "mini") + ":" + grid.page + ":" + grid.items.length;
  }

  function canX(dir: 1 | -1): boolean {
    const k = keyOf();
    if (!k) return false;
    if (blocked[blockKey(dir, k)]) return false;
    return canStep(grid, k, dir, opts());
  }

  async function step(dir: 1 | -1): Promise<void> {
    const k = keyOf();
    if (!k) return;
    const o = opts();
    const bk = blockKey(dir, k);
    const target = await stepInList(grid, k, dir, o);
    if (!target) {
      if (grid.status === "error") {
        notify("Could not load the next page");
      } else {
        blocked[bk] = true;
      }
      return;
    }
    if (player.mode === "stage") {
      navigate(itemHref(target));
    } else {
      try {
        const d = await getDetail("videos", target.id);
        const pi = toPlayerItem(d);
        if (pi) player.swap(pi);
        else notify("Could not open that video");
      } catch {
        notify("Could not open that video");
      }
    }
  }

  return {
    next() { void step(1); },
    prev() { void step(-1); },
    canNext() { return canX(1); },
    canPrev() { return canX(-1); },
  };
}
