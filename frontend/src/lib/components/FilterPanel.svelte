<script lang="ts">
  import type { Pill, SiteId } from "../query";
  import { PILLS, SITE_ORDER, toggleSiteIn } from "../query";
  import { onMount } from "svelte";
  import Icon from "./Icon.svelte";

  let {
    pill,
    sites,
    onpill,
    onsites,
    onclear,
    onclose,
  }: {
    pill: Pill;
    sites: SiteId[];
    onpill: (p: Pill) => void;
    onsites: (s: SiteId[]) => void;
    onclear: () => void;
    onclose: () => void;
  } = $props();

  let panel: HTMLDivElement | undefined;
  let closeBtn: HTMLButtonElement | undefined;

  onMount(() => closeBtn?.focus());

  // Escape closes; Tab wraps inside the panel so focus never lands in the page behind the scrim.
  function onkeydown(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      onclose();
      return;
    }
    if (e.key !== "Tab" || !panel) return;
    const items = [...panel.querySelectorAll<HTMLElement>("button:not([disabled])")];
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || !panel.contains(active))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (active === last || !panel.contains(active))) {
      e.preventDefault();
      first.focus();
    }
  }
</script>

<svelte:window {onkeydown} />

<div class="scrim" role="presentation" onclick={onclose}></div>
<div class="fpanel" role="dialog" aria-modal="true" aria-label="Filters" bind:this={panel}>
  <div class="fh">
    <b>Filters</b>
    <button class="close" type="button" aria-label="Close" bind:this={closeBtn} onclick={onclose}><Icon name="x" size={20} /></button>
  </div>
  <div class="fb">
    <section class="fsec">
      <h3>Scope</h3>
      <div class="opts" data-testid="scope-opts">
        {#each PILLS as p (p.id)}
          <button type="button" class:on={pill === p.id} aria-pressed={pill === p.id} onclick={() => onpill(p.id)}>{p.label}</button>
        {/each}
      </div>
    </section>
    <section class="fsec">
      <h3>Sites</h3>
      <div class="opts" data-testid="site-opts">
        {#each SITE_ORDER as s (s.id)}
          <button type="button" class:on={sites.includes(s.id)} aria-pressed={sites.includes(s.id)} onclick={() => onsites(toggleSiteIn(sites, s.id))}>{s.label}</button>
        {/each}
      </div>
    </section>
  </div>
  <div class="ff">
    <button type="button" onclick={onclear}>Clear all</button>
    <button type="button" class="go" onclick={onclose}>Done</button>
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 1000;
  }

  .fpanel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(380px, 100%);
    z-index: 1100;
    background: var(--bg);
    border-left: 1px solid var(--line-strong);
    display: flex;
    flex-direction: column;
  }

  .fh {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--s-3) 0 var(--s-4);
    border-bottom: 1px solid var(--line);
    font-size: var(--t-15);
  }

  .close {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    padding: 0;
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
  }

  .fb {
    flex: 1;
    overflow-y: auto;
    padding: var(--s-3);
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
  }

  .fsec {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: var(--s-3);
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }

  .fsec h3 {
    margin: 0;
    font-size: var(--t-12);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .opts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--s-2);
  }

  .opts button {
    min-height: 44px;
    padding: 0 var(--s-3);
    border-radius: 22px;
    border: 1px solid var(--line-strong);
    background: var(--bg);
    color: var(--text);
    font-size: var(--t-13);
    cursor: pointer;
  }

  .opts button:last-child:nth-child(odd) {
    grid-column: 1 / -1;
  }

  .opts button.on {
    background: var(--accent-bg);
    border-color: var(--accent);
    color: var(--accent);
  }

  .ff {
    display: flex;
    gap: var(--s-2);
    padding: var(--s-3);
    border-top: 1px solid var(--line);
  }

  .ff button {
    flex: 1;
    min-height: 44px;
    border-radius: var(--r-md);
    border: 1px solid var(--line-strong);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }

  .ff .go {
    border: 0;
    background: var(--accent);
    color: var(--bg);
    font-weight: 600;
  }
</style>
