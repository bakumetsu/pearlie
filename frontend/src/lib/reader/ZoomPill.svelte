<script lang="ts">
  import Icon from "../components/Icon.svelte";

  let {
    zoom,
    onin,
    onout,
    onreset,
  }: {
    zoom: number;
    onin: () => void;
    onout: () => void;
    onreset: () => void;
  } = $props();
</script>

<div class="pill" data-testid="zoom-pill">
  <button
    class="icon-btn"
    aria-label="Zoom out"
    disabled={zoom <= 50}
    onclick={onout}
  >
    <Icon name="minus" size={20} />
  </button>
  <button class="label-btn" aria-label="Reset zoom" onclick={onreset}>
    {zoom}&thinsp;%
  </button>
  <button
    class="icon-btn"
    aria-label="Zoom in"
    disabled={zoom >= 300}
    onclick={onin}
  >
    <Icon name="plus" size={20} />
  </button>
</div>

<style>
  .pill {
    position: absolute;
    right: 16px;
    bottom: 16px;
    display: flex;
    align-items: center;
    padding: 2px;
    border-radius: 999px;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
  }

  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: var(--text);
    cursor: pointer;
    font: inherit;
  }

  .label-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    padding: 0 var(--s-2, 8px);
    border: none;
    border-radius: 999px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    font: inherit;
    font-size: var(--t-13);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .icon-btn:disabled,
  .label-btn:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .icon-btn:hover:not(:disabled),
  .label-btn:hover:not(:disabled) {
    background: var(--line);
  }

  .icon-btn:focus-visible,
  .label-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
