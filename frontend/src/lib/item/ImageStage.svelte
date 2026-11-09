<script lang="ts">
  let { src, alt, preload = null, zoomed = $bindable(false) }: {
    src: string;
    alt: string;
    preload?: string | null;
    zoomed?: boolean;
  } = $props();

  let stageEl: HTMLDivElement | undefined = $state();
  let dragged = $state(false);
  let panStart: { x: number; y: number; sl: number; st: number } | null = null;

  function onPointerDown(e: PointerEvent): void {
    if (e.pointerType !== "mouse" || !zoomed) return;
    const el = stageEl;
    if (!el) return;
    panStart = { x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop };
    dragged = false;
  }

  function onPointerMove(e: PointerEvent): void {
    if (e.pointerType !== "mouse" || !zoomed || !panStart) return;
    if (!(e.buttons & 1)) return;
    const el = stageEl;
    if (!el) return;
    const dx = e.clientX - panStart.x;
    const dy = e.clientY - panStart.y;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) dragged = true;
    el.scrollLeft = panStart.sl - dx;
    el.scrollTop = panStart.st - dy;
  }

  function onPointerUp(): void {
    panStart = null;
    setTimeout(() => (dragged = false), 0);
  }

  function onPointerCancel(): void {
    panStart = null;
  }
</script>

<svelte:head>
  {#if preload}
    <link rel="preload" as="image" href={preload} />
  {/if}
</svelte:head>

<div
  class="stage"
  role="presentation"
  class:zoomed={zoomed}
  bind:this={stageEl}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointercancel={onPointerCancel}
>
  <button
    type="button"
    class="imgbtn"
    aria-label={zoomed ? "Fit to screen" : "Actual size"}
    onclick={() => {
      if (dragged) {
        dragged = false;
        return;
      }
      zoomed = !zoomed;
    }}
  >
    <img {src} {alt} class:zoomed={zoomed} />
  </button>
</div>

<style>
  .stage {
    position: relative;
    width: 100%;
    height: 100%;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .stage.zoomed {
    overflow: auto;
    touch-action: pan-x pan-y;
    cursor: grab;
  }
  .imgbtn {
    min-width: 0;
    min-height: 0;
    padding: 0;
    border: 0;
    background: none;
    cursor: zoom-in;
    display: block;
  }
  .stage:not(.zoomed) .imgbtn {
    width: 100%;
    height: 100%;
    max-height: 100%;
  }
  .stage.zoomed .imgbtn {
    cursor: zoom-out;
    margin: auto;
    width: auto;
    height: auto;
    flex: none;
  }
  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
  }
  .stage:not(.zoomed) img {
    width: 100%;
    height: 100%;
  }
  img.zoomed {
    max-width: none;
    max-height: none;
    width: auto;
    height: auto;
  }
</style>
