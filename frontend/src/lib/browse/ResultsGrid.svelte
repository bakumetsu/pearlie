<script lang="ts">
  import Tile from "../components/Tile.svelte";
  import type { LibraryItem, WebItem } from "../api/client";
  import { itemHref } from "../item/kinds";
  import { keyOf } from "../stores/shared.svelte";
  import type { Mode } from "./layout";
  import { zoomSize, columnCount, dealMasonry, wallRows } from "./layout";
  import { itemAspect } from "./sources";

  let {
    items,
    mode,
    zoom,
    loading,
    skeletons,
    saveStates,
    onsave,
    onnavigate,
    onopenitem,
    onopenweb,
    landscape = false,
  }: {
    items: (LibraryItem | WebItem)[];
    mode: Mode;
    zoom: number;
    loading: boolean;
    skeletons: number;
    saveStates: Record<string, "queued" | "in_library">;
    onsave: (item: WebItem) => void;
    onnavigate: (e: MouseEvent) => void;
    onopenitem?: (item: LibraryItem) => void;
    onopenweb?: (item: WebItem) => void;
    landscape?: boolean;
  } = $props();

  let width = $state(0);

  // 16:9 video cells are wider, so a row holds 4-5.
  const size = $derived(zoomSize(mode, zoom) * (landscape && mode === "grid" ? 1.6 : 1));
  const aspects = $derived(items.map(itemAspect));

  const WALL_GAP = 2;
  const MASONRY_GAP = 8;

  const rows = $derived(wallRows(aspects, width, size, WALL_GAP));
  const cols = $derived(columnCount(width, size, MASONRY_GAP));
  const dealt = $derived(dealMasonry(aspects, cols));
</script>

<div class="rg" bind:clientWidth={width} style:--list-thumb="{size}px">
  {#if loading}
    {#if mode === "list"}
      <div class="list">
        {#each Array.from({ length: skeletons }, (_u, n) => n) as i (i)}
          <div class="skeleton sk-bar"></div>
        {/each}
      </div>
    {:else}
      <div class="grid" style:--cell="{size}px">
        {#each Array.from({ length: skeletons }, (_u, n) => n) as i (i)}
          <div class="skeleton sk-thumb"></div>
        {/each}
      </div>
    {/if}
  {:else if mode === "grid"}
    <div class="grid" style:--cell="{size}px">
      {#each items as item (keyOf(item))}
        {@render tile(item, "grid", undefined)}
      {/each}
    </div>
  {:else if mode === "list"}
    <div class="list">
      {#each items as item (keyOf(item))}
        {@render tile(item, "list", undefined)}
      {/each}
    </div>
  {:else if mode === "wall"}
    {#each rows as row, r (r)}
      <div class="wall-row">
        {#each row as i (i)}
          <div class="wall-cell" style:flex="{aspects[i]} 1 0%">
            {@render tile(items[i], "wall", aspects[i])}
          </div>
        {/each}
        {#if width > 0 && r === rows.length - 1}
          {@const natural = row.reduce((s, idx) => s + aspects[idx] * size, 0) + WALL_GAP * (row.length - 1)}
          {#if natural < width}
            <div style:flex="{(width - natural) / size} 1 0%"></div>
          {/if}
        {/if}
      </div>
    {/each}
  {:else}
    <div class="masonry">
      {#each dealt as col, c (c)}
        <div class="mcol">
          {#each col as i (i)}
            {@render tile(items[i], "masonry", aspects[i])}
          {/each}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#snippet tile(item: LibraryItem | WebItem, variant: Mode, aspect: number | undefined)}
  {#if "post_id" in item}
    <Tile
      item={item as WebItem}
      variant={variant}
      aspect={aspect}
      saveState={saveStates[(item as WebItem).source + ":" + (item as WebItem).post_id] ?? "idle"}
      onsave={() => onsave(item as WebItem)}
      onopen={onopenweb ? () => onopenweb(item as WebItem) : undefined}
    />
  {:else}
    <Tile
      item={item as LibraryItem}
      variant={variant}
      aspect={aspect}
      landscape={landscape}
      href={itemHref(item as LibraryItem)}
      onnavigate={onnavigate}
      onopenitem={onopenitem}
    />
  {/if}
{/snippet}

<style>
  .rg {
    display: block;
    width: 100%;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--cell), 1fr));
    gap: 16px;
  }

  .list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .list > :global(*) {
    border-bottom: 1px solid var(--border, rgba(127, 127, 127, 0.25));
  }

  .wall-row {
    display: flex;
    gap: 2px;
    margin-bottom: 2px;
  }

  .wall-cell {
    min-width: 0;
  }

  .masonry {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }

  .mcol {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .skeleton {
    background: var(--surface);
    border-radius: var(--r-md);
  }

  .sk-thumb {
    aspect-ratio: 3 / 4;
  }

  .sk-bar {
    height: 56px;
  }
</style>
