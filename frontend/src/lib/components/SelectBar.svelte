<script lang="ts">
  import Icon from "./Icon.svelte";
  import { getApi } from "../api/client";
  import { selection } from "../library/selection.svelte";

  let { onchanged }: { onchanged: () => void } = $props();

  const api = getApi();

  function onKey(e: KeyboardEvent) {
    if (e.key === "Escape" && selection.active && !e.defaultPrevented) selection.clear();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if selection.active}
  <div class="selact" role="group" aria-label="Selection">
    <span class="n" role="status">{selection.count}</span>
    <button
      class="icon-btn"
      aria-label="Move to Trash"
      disabled={selection.count === 0 || selection.busy}
      onclick={() => selection.trashPicked(api, onchanged)}
    >
      <Icon name="trash" size={18} />
    </button>
    <button class="icon-btn" aria-label="Leave select mode" onclick={() => selection.clear()}>
      <Icon name="x" size={18} />
    </button>
  </div>
{/if}

<style>
  .selact {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: auto;
  }
  .n {
    margin-right: 6px;
    font-weight: 600;
    font-size: var(--t-14);
  }
  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border: none;
    background: none;
    color: var(--text);
    border-radius: var(--r-md);
    cursor: pointer;
  }
  .icon-btn:hover:not(:disabled) {
    background: var(--accent-bg);
  }
  .icon-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
</style>
