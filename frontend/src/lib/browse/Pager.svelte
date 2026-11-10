<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import {
    pagerState,
    pagerForm,
    pageOptions,
    rangeText,
    clampInput,
    type PageStats,
  } from "./pager";

  let {
    page,
    pages,
    hasNext,
    perPage,
    shown,
    total,
    stats,
    onpage,
    showStats = true,
    spaced = false,
    selectEl = $bindable<HTMLSelectElement | HTMLInputElement | null>(null),
  }: {
    page: number;
    pages: number | null;
    hasNext: boolean;
    perPage: number;
    shown: number;
    total: number | null;
    stats: PageStats | null;
    onpage: (p: number) => void;
    showStats?: boolean;
    spaced?: boolean;
    selectEl?: HTMLSelectElement | HTMLInputElement | null;
  } = $props();

  let fieldText = $derived(String(page));

  const ps = $derived(pagerState({ page, pages, hasNext }));
  const form = $derived(pagerForm(pages));
  const options = $derived(pages !== null ? pageOptions(pages) : null);
  const range = $derived(rangeText({ page, perPage, shown, total, stats }));

  function commitField() {
    if (pages === null) return;
    const next = clampInput(fieldText, pages);
    if (next !== null && next !== page) {
      fieldText = String(next);
      onpage(next);
    } else {
      fieldText = String(page);
    }
  }
</script>

<div class="pager-wrap" class:spaced>
<nav class="pager" aria-label="Pages">
  <button
    type="button"
    aria-label="First page"
    disabled={!ps.first}
    onclick={() => onpage(1)}
  >
    <Icon name="chevrons-left" />
  </button>
  <button
    type="button"
    aria-label="Previous page"
    disabled={!ps.prev}
    onclick={() => onpage(page - 1)}
  >
    <Icon name="chevron-left" />
  </button>

  {#if form === "full" && pages !== null}
    {#if options !== null && options.kind === "select"}
      <select
        aria-label="Page"
        value={page}
        bind:this={selectEl}
        onchange={(e) => onpage(Number(e.currentTarget.value))}
      >
        {#each options.values as n (n)}
          <option value={n}>{n} of {pages}</option>
        {/each}
      </select>
    {:else if options !== null && options.kind === "field"}
      <input
        aria-label="Page"
        inputmode="numeric"
        bind:value={fieldText}
        bind:this={selectEl}
        onkeydown={(e) => {
          if (e.key === "Enter") commitField();
        }}
        onblur={commitField}
      />
    {/if}
  {:else}
    <span class="cur">Page {page}</span>
  {/if}

  <button
    type="button"
    aria-label="Next page"
    disabled={!ps.next}
    onclick={() => onpage(page + 1)}
  >
    <Icon name="chevron-right" />
  </button>
  {#if ps.showLast && pages !== null}
    <button
      type="button"
      aria-label="Last page"
      disabled={!ps.last}
      onclick={() => onpage(pages)}
    >
      <Icon name="chevrons-right" />
    </button>
  {/if}
</nav>
  {#if showStats && range}
    <div class="range">{range}</div>
  {/if}
</div>

<style>
  .pager {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 6px;
  }

  .pager button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    background: var(--surface);
    color: var(--text);
    border-radius: var(--r-md);
    cursor: pointer;
  }

  .pager button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .pager select,
  .pager input {
    height: 44px;
    min-height: 44px;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    border-radius: var(--r-md);
  }

  .pager input {
    width: 5em;
    padding: 0 8px;
  }

  .pager select {
    padding: 0 28px 0 8px;
  }

  .cur,
  .range {
    color: var(--text);
  }

  .pager-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .pager-wrap.spaced {
    margin: 16px 0;
  }
</style>
