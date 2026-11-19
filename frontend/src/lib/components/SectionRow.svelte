<script lang="ts">
  import Icon from "./Icon.svelte";
  import type { Snippet } from "svelte";
  import { onMount } from "svelte";

  let { title, count, seeAllHref, onnavigate, hidden, rulesHref, error, onretry, wide, children }: {
    title: string;
    count?: number | null;
    seeAllHref?: string;
    onnavigate?: (e: MouseEvent) => void;
    hidden?: number;
    rulesHref?: string;
    error?: string | null;
    onretry?: () => void;
    wide?: boolean;
    children: Snippet;
  } = $props();

  let strip = $state<HTMLDivElement | undefined>();
  let scrollLeft = $state(0);
  let clientWidth = $state(0);
  let scrollWidth = $state(0);

  const canLeft = $derived(scrollLeft > 0);
  const canRight = $derived(scrollLeft + clientWidth < scrollWidth - 1);

  function updateMetrics() {
    if (strip) {
      scrollLeft = strip.scrollLeft;
      clientWidth = strip.clientWidth;
      scrollWidth = strip.scrollWidth;
    }
  }

  function scrollBy(dir: -1 | 1) {
    if (!strip) return;
    strip.scrollBy({ left: dir * strip.clientWidth * 0.8, behavior: "smooth" });
  }

  onMount(() => {
    updateMetrics();
    if (strip && typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(updateMetrics);
      ro.observe(strip);
      return () => ro.disconnect();
    }
  });
</script>

<div class="row">
  <header class="header">
    <div class="heading">
      <h2>{title}</h2>
      {#if count != null}
        <span class="count">{count}</span>
      {/if}
    </div>
    {#if seeAllHref}
      <a class="see-all" href={seeAllHref}
        aria-label="See all" onclick={onnavigate}>
        <Icon name="arrow-right" size={20} />
      </a>
    {/if}
  </header>

  {#if error}
    <div class="error-box">
      <p class="error-msg">{error}</p>
      <button class="retry-btn" onclick={onretry}>Retry</button>
    </div>
  {:else}
    <div class="strip-wrap">
      <button
        class="arrow arrow-left"
        class:hidden={!canLeft}
        aria-label="Scroll left"
        onclick={() => scrollBy(-1)}
      >
        <Icon name="chevron-left" size={20} />
      </button>
      <div class="strip no-scrollbar" class:wide bind:this={strip} onscroll={updateMetrics}>
        {@render children()}
      </div>
      <button
        class="arrow arrow-right"
        class:hidden={!canRight}
        aria-label="Scroll right"
        onclick={() => scrollBy(1)}
      >
        <Icon name="chevron-right" size={20} />
      </button>
    </div>
  {/if}

  {#if hidden != null && hidden > 0}
    <div class="footer">
      <a href={rulesHref} onclick={onnavigate}>{hidden} hidden by rules</a>
    </div>
  {/if}
</div>

<style>
  .row {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    min-width: 0;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .heading {
    display: flex;
    align-items: baseline;
    gap: var(--s-1);
  }
  h2 {
    font-size: var(--t-20);
    font-weight: 600;
    color: var(--text);
    margin: 0;
  }
  .count {
    font-size: var(--t-14);
    color: var(--muted);
  }
  .see-all {
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent);
    text-decoration: none;
  }
  .strip-wrap {
    position: relative;
    min-width: 0;
  }
  .strip {
    display: flex;
    gap: var(--s-2);
    overflow-x: auto;
    scroll-snap-type: x proximity;
    scrollbar-width: none;
    padding: var(--s-1) 0;
    min-width: 0;
    align-items: flex-start;
  }
  .strip.wide > :global(*) {
    flex-basis: max(200px, calc((100% - 4 * var(--s-2)) / 5));
  }
  .strip::-webkit-scrollbar {
    display: none;
  }
  .strip > :global(*) {
    scroll-snap-align: start;
    flex: 0 0 max(120px, calc((100% - 6 * var(--s-2)) / 7));
  }
  .arrow {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    z-index: 2;
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: rgba(0, 0, 0, 0.55);
    border: none;
    border-radius: 50%;
    color: #fff;
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s ease;
  }
  .arrow :global(svg) {
    stroke-width: 1.5;
  }
  .strip-wrap:hover .arrow {
    opacity: 1;
    pointer-events: auto;
  }
  .arrow:focus-visible {
    opacity: 1;
    pointer-events: auto;
  }
  .arrow-left {
    left: var(--s-1);
  }
  .arrow-right {
    right: var(--s-1);
  }
  @media (hover: none) {
    .arrow {
      display: none;
    }
  }
  .hidden {
    display: none;
  }
  .error-box {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--s-2);
    padding: var(--s-3);
    background: var(--danger-bg);
    border-radius: var(--r-md);
    color: var(--danger-fg);
  }
  .error-msg {
    margin: 0;
    font-size: var(--t-14);
  }
  .retry-btn {
    background: var(--danger-fg);
    color: var(--surface);
    border: none;
    border-radius: var(--r-sm);
    padding: var(--s-1) var(--s-3);
    font-size: var(--t-13);
    cursor: pointer;
  }
  .footer {
    font-size: var(--t-13);
  }
  .footer a {
    color: var(--muted);
    text-decoration: none;
  }
</style>
