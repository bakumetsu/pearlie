<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import PageBar from "./PageBar.svelte";
  import type { Mode, Fit, Dir } from "./pages";
  import type { LibraryItem } from "../api/client";

  let {
    count,
    shown,
    dir,
    thumbsOpen,
    onjump,
    onthumbs,
  }: {
    count: number;
    shown: number[];
    dir: Dir;
    thumbsOpen: boolean;
    onjump: (n: number) => void;
    onthumbs: () => void;
  } = $props();

  const label = $derived(
    shown.length <= 1
      ? `${shown[0] ?? 1} / ${count}`
      : `${Math.min(...shown)}–${Math.max(...shown)} / ${count}`,
  );
</script>

<div class="card" data-testid="bottom-card">
  <PageBar {count} {shown} {dir} onjump={onjump} />
  <span class="pos">{label}</span>
  <button
    class="chevron"
    aria-label="Thumbnails"
    aria-expanded={thumbsOpen}
    onclick={onthumbs}
  >
    <Icon name={thumbsOpen ? "chevron-down" : "chevron-up"} size={20} />
  </button>
</div>

<style>
  .card {
    position: absolute;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    width: min(720px, calc(100% - 32px));
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    border-radius: 12px;
    padding: 2px 8px;
  }

  .pos {
    flex: none;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    font-size: var(--t-13);
    color: var(--t-13);
  }

  .chevron {
    flex: none;
    min-width: 44px;
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: 0;
    border-radius: 10px;
    cursor: pointer;
    color: inherit;
    padding: 0;
  }

  .chevron:hover {
    background: var(--line);
  }

  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
