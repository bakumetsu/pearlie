<script lang="ts">
  import type { Mode } from "./layout";
  import { ZOOM_MIN, ZOOM_MAX } from "./layout";
  import { clampInput } from "./pager";
  import Icon from "../components/Icon.svelte";

  let {
    mode,
    modes,
    perPage,
    zoom,
    options,
    max,
    onmode,
    onperpage,
    onzoom,
    onzoompreview,
  }: {
    mode: Mode;
    modes: Mode[];
    perPage: number;
    zoom: number;
    options: number[];
    max: number;
    onmode: (m: Mode) => void;
    onperpage: (n: number) => void;
    onzoom: (z: number) => void;
    onzoompreview: (z: number) => void;
  } = $props();

  let custom = $state(false);
  let sheet = $state(false);
  let vw = $state(1024);
  let customVal = $state("");

  const phone = $derived(vw < 720);

  const MODE_LABELS: Record<Mode, string> = {
    grid: "Grid",
    wall: "Wall",
    masonry: "Masonry",
    list: "List",
  };

  const selectOptions = $derived.by(() => {
    const base = [...options].sort((a, b) => a - b);
    if (!base.includes(perPage)) {
      const i = base.findIndex((v) => v > perPage);
      if (i === -1) base.push(perPage);
      else base.splice(i, 0, perPage);
    }
    return base;
  });

  function onPerPageChange(e: Event) {
    const el = e.currentTarget as HTMLSelectElement;
    if (el.value === "custom") {
      custom = true;
      customVal = String(perPage);
      el.value = String(perPage);
    } else {
      onperpage(Number(el.value));
    }
  }

  function commitCustom() {
    const n = clampInput(customVal, max);
    if (n !== null && n !== perPage) onperpage(n);
    custom = false;
    customVal = "";
  }
</script>

<svelte:window bind:innerWidth={vw} />

{#snippet controls()}
  <div class="pp">
    <select aria-label="Per page" value={String(perPage)} onchange={onPerPageChange}>
      {#each selectOptions as n (n)}
        <option value={String(n)}>{n}</option>
      {/each}
      <option value="custom">Custom...</option>
    </select>
    {#if custom}
      <input
        aria-label="Custom per page"
        inputmode="numeric"
        class="custom-input"
        placeholder={String(max)}
        bind:value={customVal}
        onkeydown={(e) => e.key === "Enter" && commitCustom()}
        onblur={commitCustom}
      />
    {/if}
  </div>
  <div class="modes">
    {#each modes as m (m)}
      <button
        type="button"
        aria-label={MODE_LABELS[m]}
        aria-pressed={mode === m}
        class:active={mode === m}
        onclick={() => onmode(m)}
      >
        <Icon name={m} />
      </button>
    {/each}
  </div>
  <div class="zoom-wrap">
    <input
      type="range"
      aria-label="Zoom"
      min={ZOOM_MIN}
      max={ZOOM_MAX}
      step="1"
      value={zoom}
      oninput={(e) => onzoompreview(Number((e.currentTarget as HTMLInputElement).value))}
      onchange={(e) => onzoom(Number((e.currentTarget as HTMLInputElement).value))}
    />
  </div>
{/snippet}

{#if !phone}
  <div class="viewbar">{@render controls()}</div>
{:else}
  <button
    type="button"
    class="viewbtn"
    aria-label="View"
    aria-haspopup="dialog"
    onclick={() => (sheet = true)}
  >
    <Icon name="sliders" />
  </button>
  {#if sheet}
    <div class="backdrop" role="presentation" onclick={() => (sheet = false)}></div>
    <div class="sheet" role="dialog" aria-label="View settings">
      {@render controls()}
      <button type="button" class="done" onclick={() => (sheet = false)}>Done</button>
    </div>
  {/if}
{/if}

<style>
  .viewbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
  }

  .pp {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .pp select {
    height: 44px;
    min-width: 5.5em;
    padding: 0 8px;
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    border-radius: var(--r-md, 6px);
    background: var(--surface, #1e1e1e);
    color: inherit;
    font-size: 0.9rem;
  }

  .custom-input {
    width: 4.5em;
    height: 44px;
    padding: 0 8px;
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    border-radius: var(--r-md, 6px);
    background: var(--surface, #1e1e1e);
    color: inherit;
    font-size: 0.9rem;
  }

  .modes {
    display: flex;
    gap: 4px;
  }

  .modes button {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    border-radius: var(--r-md, 6px);
    background: var(--surface, #1e1e1e);
    color: inherit;
    cursor: pointer;
    padding: 0;
  }

  .modes button.active {
    border-color: var(--accent, #4fc3f7);
    background: color-mix(in srgb, var(--accent, #4fc3f7) 15%, transparent);
  }

  .zoom-wrap {
    flex: 1;
    min-width: 80px;
  }

  .zoom-wrap input[type="range"] {
    width: 100%;
    height: 44px;
    accent-color: var(--accent, #4fc3f7);
  }

  .viewbtn {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    border-radius: var(--r-md, 6px);
    background: var(--surface, #1e1e1e);
    color: inherit;
    cursor: pointer;
    padding: 0;
  }

  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 1000;
  }

  .sheet {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--surface, #1e1e1e);
    border-top: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    padding: 16px;
    z-index: 1001;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .done {
    height: 44px;
    border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
    border-radius: var(--r-md, 6px);
    background: var(--surface, #1e1e1e);
    color: inherit;
    font-size: 1rem;
    cursor: pointer;
    margin-top: 4px;
  }
</style>
