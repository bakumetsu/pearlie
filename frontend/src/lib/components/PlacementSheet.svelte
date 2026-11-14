<script lang="ts">
  import Icon from "./Icon.svelte";
  import { placement as defaultStore } from "../stores/placement.svelte";

  let { store = defaultStore }: { store?: typeof defaultStore } = $props();

  let sheetEl: HTMLDivElement | undefined = $state();
  let opener: HTMLElement | null = null;

  // Focus moves into the sheet on open and back to the opener (the Save button) on close.
  $effect(() => {
    if (store.item && sheetEl) {
      opener = document.activeElement as HTMLElement | null;
      sheetEl.focus();
      return () => {
        opener?.focus();
        opener = null;
      };
    }
  });

  function onkeydown(e: KeyboardEvent) {
    if (store.item && e.key === "Escape") {
      e.preventDefault();
      store.cancel();
    }
  }

  const s = $derived(store.suggestion);
  const kind = $derived(store.kind);
  const line = $derived.by(() => {
    if (kind === "oneshot") return "Oneshot";
    const base = s && s.kind === "series" && s.series ? s.series : "";
    const vol = s && s.kind === "series" && s.number ? ` · vol ${s.number}` : "";
    return base ? `Series  ${base}${vol}` : "Series";
  });
  const note = $derived.by(() => {
    if (!s || kind !== s.kind) return "";
    if (s.moves_first) return "The first book moves into this series.";
    if (s.reason === "absorb") return "Joins an existing series by name.";
    if (s.joins_existing) return "Joins an existing series.";
    return "";
  });
</script>

<svelte:window {onkeydown} />

{#if store.item}
  <div class="scrim" role="presentation" onclick={() => store.cancel()}></div>
  <div class="sheet" bind:this={sheetEl} tabindex="-1" role="dialog" aria-modal="true" aria-label="Where to save" data-testid="placement-sheet">
    <div class="head">
      <span class="line" data-testid="placement-line">{store.loading ? "Checking…" : line}</span>
      <button class="icon-btn" aria-label="Close" onclick={() => store.cancel()}>
        <Icon name="x" size={18} />
      </button>
    </div>
    {#if store.error}
      <p class="note err" role="alert">Could not check the folder. Pearlie will decide.</p>
    {:else if note}
      <p class="note">{note}</p>
    {/if}
    <div class="actions">
      {#if !store.loading && !store.error}
        <button class="chip" data-testid="placement-toggle" onclick={() => store.toggle()}>
          {kind === "series" ? "Make oneshot" : "Make series"}
        </button>
      {/if}
      <button class="save" data-testid="placement-save" disabled={store.loading} onclick={() => store.confirm()}>
        Save
      </button>
    </div>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 900;
    background: rgb(0 0 0 / 0.5);
  }
  .sheet {
    position: fixed;
    z-index: 901;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    padding: var(--s-3) 16px calc(var(--s-3) + env(safe-area-inset-bottom, 0px));
    background: var(--surface);
    border-top: 1px solid var(--line-strong);
    border-radius: var(--r-md) var(--r-md) 0 0;
    color: var(--text);
  }
  @media (min-width: 720px) {
    .sheet {
      left: 50%;
      right: auto;
      bottom: auto;
      top: 50%;
      width: 420px;
      transform: translate(-50%, -50%);
      border: 1px solid var(--line-strong);
      border-radius: var(--r-md);
    }
  }
  .sheet:focus {
    outline: none;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-2);
  }
  .line {
    font-size: var(--t-15);
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .note {
    margin: 0;
    font-size: var(--t-13);
    color: var(--muted);
  }
  .note.err {
    color: var(--danger-fg);
  }
  .actions {
    display: flex;
    gap: var(--s-2);
    justify-content: flex-end;
    flex-wrap: wrap;
  }
  .icon-btn,
  .chip,
  .save {
    min-height: 44px;
    min-width: 44px;
    padding: 0 var(--s-3);
    border-radius: var(--r-sm);
    border: 1px solid var(--line-strong);
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .icon-btn {
    border: 0;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .save {
    background: var(--accent-bg);
    color: var(--accent);
    font-weight: 600;
  }
  .save:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
