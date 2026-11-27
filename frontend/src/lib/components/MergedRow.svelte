<script lang="ts">
  import SectionRow from "./SectionRow.svelte";
  import Tile from "./Tile.svelte";
  import type { WebItem } from "../api/client";
  import { SITE_ORDER } from "../query";

  let { items, status, error, hidden = 0, seeAllHref = "/see-all?source=merged", rulesHref = "/rules", onretry, onnavigate, tileHref, saveState, savedHref, onsave, onopen }: {
    items: WebItem[];
    status: "idle" | "loading" | "done" | "error";
    error?: string | null;
    hidden?: number;
    seeAllHref?: string;
    rulesHref?: string;
    onretry?: () => void;
    onnavigate?: (e: MouseEvent) => void;
    tileHref?: (item: WebItem) => string | undefined;
    saveState?: (item: WebItem) => "idle" | "queued" | "in_library";
    savedHref?: (item: WebItem) => string | undefined;
    onsave?: (item: WebItem) => void;
    onopen?: (item: WebItem) => void;
  } = $props();

  const SKELETONS = [0, 1, 2, 3, 4, 5, 6];
  const letter = (source: string) => SITE_ORDER.find((s) => s.id === source)?.label[0] ?? source[0]?.toUpperCase() ?? "";
</script>

{#if status === "loading" || status === "idle"}
  <div class="skeleton-row" aria-busy="true">
    <div class="skeleton-title"></div>
    <div class="skeleton-items">
      {#each SKELETONS as s (s)}
        <div class="skeleton"></div>
      {/each}
    </div>
  </div>
{:else}
  <SectionRow title="Latest from your sites" {seeAllHref} {hidden} {rulesHref} {error} {onretry} {onnavigate}>
    {#if items.length === 0 && status === "done"}
      <p class="empty">Nothing to show. The sites gave no posts, or rules hid them.</p>
    {:else}
      {#each items as item (item.source + ":" + item.post_id)}
        <Tile {item} badge={letter(item.source)} href={tileHref?.(item)} saveState={saveState?.(item)} savedHref={savedHref?.(item)} onsave={() => onsave?.(item)} onopen={() => onopen?.(item)} />
      {/each}
    {/if}
  </SectionRow>
{/if}

<style>
  .skeleton-row {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }
  .skeleton-title {
    width: 120px;
    height: 24px;
    border-radius: var(--r-sm);
    background: var(--surface);
    animation: pulse 1.5s ease-in-out infinite;
  }
  .skeleton-items {
    display: flex;
    gap: var(--s-2);
    overflow: hidden;
  }
  .skeleton {
    flex: 0 0 160px;
    width: 160px;
    height: 160px;
    border-radius: var(--r-md);
    background: var(--surface);
    animation: pulse 1.5s ease-in-out infinite;
  }
  .empty {
    flex: 1 1 100%;
    margin: 0;
    font-size: var(--t-14);
    color: var(--muted);
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
</style>
