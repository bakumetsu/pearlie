<script lang="ts">
  import { untrack } from "svelte";
  import { sortLabel, RATING_LABELS } from "./filters";

  let {
    sort,
    rating,
    sorts,
    ratings,
    orderBlocked = false,
    onapply,
    onclose,
  }: {
    sort: string;
    rating: string[];
    sorts: string[];
    ratings: string[];
    orderBlocked?: boolean;
    onapply: (next: { sort: string; rating: string[] }) => void;
    onclose: () => void;
  } = $props();

  // Draft state: nothing is sent until Apply, so several changes are one request.
  let dSort = $state(untrack(() => sort));
  let dRating = $state<string[]>(untrack(() => [...rating]));

  function toggle(r: string) {
    dRating = dRating.includes(r) ? dRating.filter((x) => x !== r) : [...dRating, r];
  }

  function apply() {
    onapply({ sort: dSort, rating: ratings.filter((r) => dRating.includes(r)) });
  }
</script>

<div class="backdrop" role="presentation" onclick={onclose}></div>
<div class="sheet" role="dialog" aria-label="Filters">
  {#if sorts.length > 1}
    <p class="group-label">Sort</p>
    {#if orderBlocked}<p class="hint">Sort is off while the search words fill the site's tag limit.</p>{/if}
    <div class="chips" role="group" aria-label="Sort">
      {#each sorts as o (o)}
        {@const v = o === "newest" ? "" : o}
        <button type="button" class="chip" aria-pressed={dSort === v} disabled={orderBlocked} onclick={() => (dSort = v)}>{sortLabel(o)}</button>
      {/each}
    </div>
  {/if}
  {#if ratings.length > 0}
    <p class="group-label">Rating</p>
    <div class="chips" role="group" aria-label="Rating">
      {#each ratings as r (r)}
        <button type="button" class="chip" aria-pressed={dRating.includes(r)} onclick={() => toggle(r)}>{RATING_LABELS[r] ?? r}</button>
      {/each}
    </div>
  {/if}
  <button type="button" class="apply" onclick={apply}>Apply</button>
</div>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 30; background: rgba(0, 0, 0, 0.5); }
  .sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 31; padding: var(--s-4); border-radius: var(--s-4) var(--s-4) 0 0; background: var(--surface); color: var(--text); border-top: 1px solid var(--text); }
  .group-label { margin: var(--s-4) 0 var(--s-2); font-weight: 700; }
  .hint { margin: 0 0 var(--s-2); font-size: 0.875rem; color: var(--muted); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .chip { min-height: 44px; padding: 0 var(--s-4); border: 1px solid var(--text); border-radius: var(--s-4); background: none; color: var(--text); cursor: pointer; font: inherit; }
  .chip[aria-pressed="true"] { background: var(--text); color: var(--surface); }
  .chip:disabled { opacity: 0.5; cursor: not-allowed; }
  .apply { width: 100%; min-height: 44px; margin-top: var(--s-4); border: none; border-radius: var(--s-2); background: var(--text); color: var(--surface); cursor: pointer; font: inherit; font-weight: 700; }
</style>
