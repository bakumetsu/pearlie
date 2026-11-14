<script lang="ts">
  import Icon from "../components/Icon.svelte";

  let {
    title,
    index,
    total,
    hasSeries,
    onprev,
    onnext,
    onlist,
  }: {
    title: string;
    index: number;
    total: number;
    hasSeries: boolean;
    onprev: () => void;
    onnext: () => void;
    onlist: () => void;
  } = $props();

  const canPrev = $derived(index > 1);
  const canNext = $derived(index < total);
</script>

<div class="pill" data-testid="book-pill">
  {#if !hasSeries}
    <span class="label">{title}</span>
  {:else}
    <button class="btn" aria-label="Previous book" disabled={!canPrev} onclick={onprev}>
      <Icon name="chevron-left" size={20} />
    </button>
    <button class="btn center" aria-label="Book list" onclick={onlist}>
      <span class="label">{title}</span>
      <span class="num">{index}/{total}</span>
    </button>
    <button class="btn" aria-label="Next book" disabled={!canNext} onclick={onnext}>
      <Icon name="chevron-right" size={20} />
    </button>
  {/if}
</div>

<style>
  .pill {
    position: absolute;
    top: 4px;
    right: calc(8px + var(--sfw-inset));
    display: flex;
    align-items: center;
    padding: 4px;
    min-height: 52px;
    box-sizing: border-box;
    border-radius: 999px;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    min-width: 44px;
    min-height: 44px;
    padding: 0 8px;
    border: none;
    border-radius: 999px;
    background: none;
    color: var(--text);
    font: inherit;
    cursor: pointer;
  }

  .btn:hover:not(:disabled) {
    background: var(--line);
  }

  .btn:disabled {
    opacity: 0.35;
    cursor: default;
  }

  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .pill > .label {
    padding: 0 12px;
  }

  .label {
    font-size: var(--t-13);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 160px;
  }

  .num {
    font-size: var(--t-13);
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  @media (max-width: 600px) {
    .center .label {
      display: none;
    }
  }
</style>
