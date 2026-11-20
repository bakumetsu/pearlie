<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon from "../components/Icon.svelte";

  let {
    ready = true,
    cover,
    backdrop,
    backdropStrength = 1,
    title = "",
    sub = [],
    by = "",
    progress,
    meta,
    tools,
    onback,
    bar,
    read,
    actions,
    children,
    side,
  }: {
    ready?: boolean;
    cover?: string;
    backdrop?: string;
    backdropStrength?: number;
    title?: string;
    sub?: string[];
    by?: string;
    progress?: number;
    meta?: Snippet;
    tools?: Snippet;
    onback: () => void;
    bar?: Snippet;
    read?: Snippet;
    actions?: Snippet;
    children?: Snippet;
    side?: Snippet;
  } = $props();

  let menuOpen = $state(false);
  let actsEl = $state<HTMLElement>();
  const bg = $derived(backdrop ? `url(${JSON.stringify(backdrop)})` : "");
  const lines = $derived(sub.filter(Boolean));
</script>

<svelte:window
  onpointerdown={(e) => { if (menuOpen && actsEl && !actsEl.contains(e.target as Node)) menuOpen = false; }}
  onkeydown={(e) => { if (e.key === "Escape" && menuOpen) menuOpen = false; }}
/>

<div class="bp">
  {#if bg && backdropStrength > 0}
    <div class="backdrop" style:background-image={bg} style:opacity={0.35 * backdropStrength} aria-hidden="true"></div>
  {/if}
  <header class="bar">
    <button class="ib" type="button" aria-label="Back" onclick={onback}><Icon name="arrow-left" size={20} /></button>
    {#if bar}<div class="barx">{@render bar()}</div>{/if}
  </header>

  {#if !ready}
    <div class="rest">{@render children?.()}</div>
  {:else}
    <div class="cols">
      <main class="main">
        <section class="hero">
          <div class="lc">
            <img class="cover" src={cover} alt="" />
            {@render read?.()}
          </div>
          <div class="info">
            <h1 class="title">{title}</h1>
            {#each lines as l (l)}<p class="sub">{l}</p>{/each}
            {#if by}<p class="by">{by}</p>{/if}
            {@render meta?.()}
            {#if progress !== undefined}
              <div class="ratio" aria-hidden="true"><i style:width={Math.round(Math.min(1, Math.max(0, progress)) * 100) + "%"}></i></div>
            {/if}
            {#if actions || tools}
              <div class="acts" bind:this={actsEl}>
                {#if actions}
                <button class="ib" type="button" aria-label="More actions" title="More actions" aria-haspopup="menu" aria-expanded={menuOpen} onclick={() => (menuOpen = !menuOpen)}>
                  <Icon name="ellipsis" size={20} />
                </button>
                {#if menuOpen}
                  <div class="menu" role="menu" tabindex="-1" onclick={() => (menuOpen = false)} onkeydown={(e) => { if (e.key === "Escape") menuOpen = false; }}>{@render actions()}</div>
                {/if}
                {/if}
                {#if tools}<span class="tl">{@render tools()}</span>{/if}
              </div>
            {/if}
          </div>
        </section>
        {@render children?.()}
      </main>
      {#if side}<aside class="side">{@render side()}</aside>{/if}
    </div>
  {/if}
</div>

<style>
  .bp { position: relative; min-height: 100%; padding: 0 var(--gutter) var(--s-6); min-width: 0; }
  .backdrop { position: absolute; inset: 0 0 auto 0; height: 420px; background-size: cover; background-position: center; filter: blur(40px); opacity: .35; mask-image: linear-gradient(#000, transparent); -webkit-mask-image: linear-gradient(#000, transparent); pointer-events: none; z-index: 0; }
  .bar, .cols, .rest { position: relative; z-index: 1; }
  .bar { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2) 0; }
  .barx { display: flex; gap: var(--s-2); margin-left: auto; }
  .bp :global(.ib) { min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line-strong); border-radius: var(--r-md); background: rgb(20 20 24 / .6); color: var(--text); cursor: pointer; text-decoration: none; font: inherit; }
  .bp :global(.ib:disabled) { opacity: .5; cursor: default; }
  .bp :global(.btn) { min-height: 44px; display: inline-flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-4); border: 1px solid var(--line-strong); border-radius: var(--r-md); background: transparent; color: var(--text); font: inherit; cursor: pointer; }
  .bp :global(.btn.primary) { background: #fff; color: #111; border-color: #fff; font-weight: 600; }
  .bp :global(.ib:focus-visible), .bp :global(.btn:focus-visible), .bp :global(.chip:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
  .cols { display: grid; grid-template-columns: 1fr; gap: var(--s-5); }
  .main { min-width: 0; }
  .hero { display: flex; align-items: stretch; gap: var(--s-4); text-align: left; padding-top: var(--s-2); }
  .lc { display: flex; flex-direction: column; gap: var(--s-2); width: 160px; flex: none; }
  .lc :global(.btn) { width: 100%; justify-content: center; }
  .cover { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: var(--r-md); background: var(--surface); }
  .info { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-width: 0; flex: 1; }
  .title { margin: 0; font-size: var(--t-20); line-height: 1.15; font-weight: 800; overflow-wrap: anywhere; }
  .sub { margin: 0; font-size: 14px; overflow-wrap: anywhere; }
  .by { margin: 0; color: var(--muted); font-size: var(--t-13); }
  .ratio { width: 200px; max-width: 100%; height: 4px; background: var(--line); border-radius: 4px; overflow: hidden; }
  .ratio i { display: block; height: 100%; background: var(--progress); }
  .acts { position: relative; align-self: stretch; margin-top: auto; display: flex; align-items: center; gap: var(--s-2); }
  .acts :global(.ib) { background: transparent; border-color: transparent; }
  .tl { margin-left: auto; display: flex; gap: var(--s-2); }
  .menu { position: absolute; left: 0; bottom: 52px; z-index: 5; min-width: 220px; background: var(--surface); border: 1px solid var(--line-strong); border-radius: var(--r-md); padding: var(--s-1); display: flex; flex-direction: column; box-shadow: 0 8px 24px rgb(0 0 0 / .5); }
  .menu :global(.mi) { min-height: 44px; display: flex; align-items: center; gap: var(--s-3); padding: 0 var(--s-3); border: 0; border-radius: 6px; background: transparent; color: var(--text); font: inherit; text-align: left; text-decoration: none; cursor: pointer; }
  .menu :global(.mi:hover) { background: var(--bg); }
  .menu :global(.mi:disabled) { opacity: .5; cursor: default; }
  .menu :global(.mi:focus-visible) { outline: 2px solid var(--accent); outline-offset: -2px; }
  .side { display: flex; flex-direction: column; gap: var(--s-4); background: transparent; border: 0; padding: 0; min-width: 0; }
  @media (min-width: 900px) {
    .cols { grid-template-columns: 1fr 260px; align-items: start; }
    .lc { width: 200px; }
    .title { font-size: 30px; }
    .sub { font-size: 16px; }
    .side { position: sticky; top: var(--s-4); max-height: calc(100vh - 2 * var(--s-4)); overflow-y: auto; }
  }
  @media (min-width: 1600px) {
    .cols { grid-template-columns: 1fr 320px; }
    .info { max-inline-size: var(--measure); }
  }
</style>
