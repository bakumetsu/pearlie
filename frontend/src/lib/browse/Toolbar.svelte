<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import FilterSheet from "./FilterSheet.svelte";
  import { ORDER_LABELS, RATING_LABELS } from "./filters";

  let {
    order,
    rating,
    orders,
    ratings,
    orderBlocked = false,
    onapply,
  }: {
    order: string;
    rating: string[];
    orders: string[];
    ratings: string[];
    orderBlocked?: boolean;
    onapply: (next: { order: string; rating: string[] }) => void;
  } = $props();

  let vw = $state(1024);
  let sheet = $state(false);
  let ratingOpen = $state(false);
  let wrapEl: HTMLDivElement | undefined = $state();
  let ratingBtn: HTMLButtonElement | undefined = $state();

  const phone = $derived(vw < 640);
  const count = $derived((order ? 1 : 0) + (rating.length ? 1 : 0));

  function pickRating(r: string, on: boolean) {
    const next = on ? [...rating, r] : rating.filter((x) => x !== r);
    onapply({ order, rating: ratings.filter((x) => next.includes(x)) });
  }
</script>

<svelte:window
  bind:innerWidth={vw}
  onpointerdown={(e) => { if (ratingOpen && wrapEl && !wrapEl.contains(e.target as Node)) ratingOpen = false; }}
  onkeydown={(e) => { if (ratingOpen && e.key === "Escape") { ratingOpen = false; ratingBtn?.focus(); } }}
/>

{#if phone}
  <button type="button" class="tbtn" aria-label="Filters" aria-haspopup="dialog" onclick={() => (sheet = true)}>
    <Icon name="sliders" />
    {#if count > 0}<span class="badge" data-testid="filter-badge">{count}</span>{/if}
  </button>
  {#if sheet}
    <FilterSheet {order} {rating} {orders} {ratings} {orderBlocked} onapply={(n) => { sheet = false; onapply(n); }} onclose={() => (sheet = false)} />
  {/if}
{:else}
  {#if orders.length > 1}
    <label class="dd" class:disabled={orderBlocked} title={orderBlocked ? "Order is off while the search words fill the site's tag limit" : undefined}>
      <Icon name="order" size={16} />
      <select aria-label="Order" value={order} disabled={orderBlocked} onchange={(e) => onapply({ order: (e.currentTarget as HTMLSelectElement).value === "newest" ? "" : (e.currentTarget as HTMLSelectElement).value, rating })}>
        {#each orders as o (o)}
          <option value={o === "newest" ? "" : o}>{ORDER_LABELS[o] ?? o}</option>
        {/each}
      </select>
    </label>
  {/if}
  {#if ratings.length > 0}
    <div class="dd-wrap" bind:this={wrapEl}>
      <button type="button" class="dd" bind:this={ratingBtn} aria-label="Rating" aria-haspopup="true" aria-expanded={ratingOpen} onclick={() => (ratingOpen = !ratingOpen)}>
        <Icon name="shield" size={16} />
        <span>{rating.length ? rating.map((r) => RATING_LABELS[r] ?? r).join(", ") : "Rating"}</span>
      </button>
      {#if ratingOpen}
        <div class="menu" role="group" aria-label="Rating">
          {#each ratings as r (r)}
            <label class="opt">
              <input type="checkbox" checked={rating.includes(r)} onchange={(e) => pickRating(r, (e.currentTarget as HTMLInputElement).checked)} />
              {RATING_LABELS[r] ?? r}
            </label>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
{/if}

<style>
  .tbtn, .dd { position: relative; min-height: 44px; display: inline-flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-4); border: 1px solid var(--text); border-radius: var(--s-2); background: var(--surface); color: var(--text); cursor: pointer; font: inherit; }
  .tbtn { min-width: 44px; justify-content: center; padding: 0; }
  .dd select { min-height: 44px; border: none; background: transparent; color: inherit; font: inherit; }
  .dd.disabled { opacity: 0.5; cursor: not-allowed; }
  .badge { position: absolute; top: -6px; right: -6px; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px; background: var(--text); color: var(--surface); font-size: 0.75rem; display: grid; place-items: center; }
  .dd-wrap { position: relative; }
  .menu { position: absolute; top: 100%; left: 0; margin-top: var(--s-2); z-index: 20; display: flex; flex-direction: column; min-width: 12em; padding: var(--s-2); border: 1px solid var(--text); border-radius: var(--s-2); background: var(--surface); }
  .opt { min-height: 44px; display: flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-2); cursor: pointer; color: var(--text); }
</style>
