<script lang="ts">
  import type { SiteId } from "../query";
  import { SITE_ORDER, toggleSiteIn } from "../query";

  let { sites, onsites }: { sites: SiteId[]; onsites: (s: SiteId[]) => void } = $props();
</script>

<div class="marks" role="group" aria-label="Sites">
  {#each SITE_ORDER as s (s.id)}
    {@const on = sites.includes(s.id)}
    <button
      class="mark-btn"
      type="button"
      title={s.label}
      aria-label={s.label}
      aria-pressed={on}
      onclick={() => onsites(toggleSiteIn(sites, s.id))}
    >
      <span class="mark-visual" class:active={on}>
        <span class="mk" aria-hidden="true">{s.label[0]}</span>
        {#if on}<span class="mk-name">{s.label}</span>{/if}
      </span>
    </button>
  {/each}
</div>

<style>
  .marks {
    display: flex;
    gap: var(--s-1);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .mark-btn {
    display: grid;
    place-items: center;
    flex: none;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    border-radius: var(--r-md);
  }

  .mark-visual {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 10px;
    border-radius: var(--r-md);
    background: var(--surface);
    border: 1px solid var(--line);
    color: var(--muted);
    white-space: nowrap;
    font-size: var(--t-13);
  }

  .mark-visual.active {
    background: var(--accent-bg);
    border-color: var(--accent);
    color: var(--accent);
  }

  .mk {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: var(--line-strong);
    color: var(--text);
    font-size: 11px;
    font-weight: 700;
  }

  .active .mk {
    background: var(--accent);
    color: var(--bg);
  }
</style>
