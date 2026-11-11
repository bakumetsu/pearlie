<script lang="ts">
  import { untrack } from "svelte";
  import Icon from "../components/Icon.svelte";
  import type { Zoom } from "./zoomModel.svelte";

  let { zoom, onhide }: { zoom: Zoom; onhide?: () => void } = $props();

  let bar: HTMLDivElement | undefined = $state();
  let announced = $state(untrack(() => zoom.percent));

  let first = true;
  $effect(() => {
    const p = zoom.percent;
    if (first) { first = false; announced = p; return; }
    const t = setTimeout(() => { announced = p; }, 400);
    return () => clearTimeout(t);
  });

  $effect.pre(() => {
    if (!zoom.active && bar && bar.contains(document.activeElement)) onhide?.();
  });
</script>

{#if zoom.active}
  <div
    class="zoombar"
    data-zoombar
    bind:this={bar}
  >
    <button
      type="button"
      class="zbtn"
      aria-label="Zoom out"
      disabled={zoom.scale <= zoom.min + 1e-6}
      onclick={() => zoom.stepOut()}
    >
      <Icon name="minus" size={20} />
    </button>
    <button
      type="button"
      class="zbtn zbtn-pct"
      aria-label={`Fit to screen, now ${zoom.percent}%`}
      onclick={() => zoom.fit()}
    >{zoom.percent}%</button>
    <button
      type="button"
      class="zbtn"
      aria-label="Zoom in"
      disabled={zoom.scale >= zoom.max - 1e-6}
      onclick={() => zoom.stepIn()}
    >
      <Icon name="plus" size={20} />
    </button>
    <span class="sr-only" role="status" aria-live="polite">Zoom {announced} percent</span>
  </div>
{/if}

<style>
  .zoombar {
    position: absolute;
    right: 12px;
    bottom: 12px;
    display: flex;
    background: rgba(0, 0, 0, 0.5);
    color: #fff;
    border-radius: 8px;
    outline: 1px solid rgba(255, 255, 255, 0.2);
    z-index: 2;
  }
  .zbtn {
    min-width: 44px;
    min-height: 44px;
    background: none;
    border: 0;
    color: inherit;
    cursor: pointer;
    font: inherit;
  }
  .zbtn:disabled {
    opacity: 0.4;
  }
  .zbtn-pct {
    font-size: 14px;
    min-width: 52px;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }
</style>
