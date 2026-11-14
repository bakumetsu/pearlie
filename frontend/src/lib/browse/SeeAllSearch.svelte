<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import ChipField from "../components/ChipField.svelte";
  import { commitText, parseQuery, serialiseQuery } from "../query";

  // `value` is the committed search (the URL `q`). The bar edits a draft; Enter or the icon commits it.
  let { value, web, onsubmit }: { value: string; web: boolean; onsubmit: (q: string) => void } = $props();

  let draftChips = $derived(parseQuery(value));
  let draftText = $derived(value);
  let pending = $state("");

  const filled = $derived(web ? draftChips.length > 0 || pending.trim() !== "" : draftText.trim() !== "");

  function submit() {
    if (web) {
      const chips = pending.trim() ? commitText(draftChips, pending) : draftChips;
      pending = "";
      onsubmit(serialiseQuery(chips));
    } else {
      onsubmit(draftText.trim());
    }
  }

  function clear() {
    draftChips = [];
    draftText = "";
    pending = "";
    onsubmit("");
  }
</script>

<!-- One Enter runs the search, also with a word still typed: capture it before the chip field turns it into a chip. -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="bar"
  role="search"
  onkeydowncapture={(e) => {
    if (web && e.key === "Enter" && pending.trim() && e.target instanceof HTMLInputElement) {
      e.preventDefault();
      e.stopPropagation();
      submit();
    }
  }}
>
  {#if web}
    <ChipField bind:pending chips={draftChips} onchange={(c) => (draftChips = c)} onsubmit={submit} label="Search this site">
      {#snippet trailing()}
        <span class="tail">
          {#if filled}
            <button class="ibtn" type="button" aria-label="Clear search" onclick={clear}><Icon name="x" size={18} /></button>
          {/if}
          <button class="ibtn" type="button" aria-label="Search" onclick={submit}><Icon name="search" size={20} /></button>
        </span>
      {/snippet}
    </ChipField>
  {:else}
    <div class="field">
      <span class="lead"><Icon name="search" size={16} /></span>
      <input
        class="text"
        type="search"
        aria-label="Search the library"
        placeholder="Search the library"
        autocomplete="off"
        bind:value={draftText}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
      />
      <span class="tail">
        {#if filled}
          <button class="ibtn" type="button" aria-label="Clear search" onclick={clear}><Icon name="x" size={18} /></button>
        {/if}
        <button class="ibtn" type="button" aria-label="Search" onclick={submit}><Icon name="search" size={20} /></button>
      </span>
    </div>
  {/if}
</div>

<style>
  .bar { width: 100%; margin-top: var(--s-4); }
  .field { display: flex; align-items: center; gap: var(--s-1); min-height: 44px; padding: 0 var(--s-2); background: var(--surface); border: 1px solid var(--line-strong); border-radius: var(--r-lg); }
  .field:focus-within { border-color: var(--accent); }
  .lead { display: flex; color: var(--muted); flex-shrink: 0; }
  .text { flex: 1; min-width: 0; min-height: 44px; border: none; background: none; color: var(--text); font-size: var(--t-14); outline: none; }
  .tail { display: inline-flex; align-items: center; margin-left: auto; }
  .ibtn { display: grid; place-items: center; width: 44px; height: 44px; padding: 0; border: none; background: none; color: var(--muted); cursor: pointer; border-radius: var(--r-sm); }
  .ibtn:hover { color: var(--text); }
</style>
