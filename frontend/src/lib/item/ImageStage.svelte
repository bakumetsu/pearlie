<script lang="ts">
  import { wheelFactor, type Zoom } from "./zoomModel.svelte";

  let { src, alt, preload = null, zoom }: {
    src: string;
    alt: string;
    preload?: string | null;
    zoom: Zoom;
  } = $props();

  let stageEl: HTMLDivElement | undefined = $state();
  let imgEl: HTMLImageElement | undefined = $state();
  let gesture = $state(false);
  let animate = $state(false);
  let swallowClick = false;

  let drag: { id: number; x: number; y: number; moved: boolean } | null = null;
  let activePointers = new Set<number>();
  let pendingDx = 0;
  let pendingDy = 0;
  let last: { x: number; y: number } | null = null;
  let rafId = 0;
  let snapTimer: ReturnType<typeof setTimeout> | null = null;

  function measure(): void {
    if (stageEl && imgEl) {
      zoom.setSizes(stageEl.clientWidth, stageEl.clientHeight, imgEl.naturalWidth, imgEl.naturalHeight);
    }
  }

  function centreOf(clientX: number, clientY: number): { x: number; y: number } {
    const rect = stageEl!.getBoundingClientRect();
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  }

  function scheduleSnap(): void {
    if (snapTimer !== null) clearTimeout(snapTimer);
    snapTimer = setTimeout(() => {
      snapTimer = null;
      zoom.snap();
    }, 150);
  }

  $effect(() => {
    const el = stageEl;
    if (!el) return;
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(el);
    return () => ro.disconnect();
  });

  $effect(() => {
    const el = stageEl;
    if (!el) return;
    function onWheel(e: WheelEvent): void {
      if (!imgEl || imgEl.naturalWidth <= 0) return;
      if (!e.ctrlKey && Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      e.preventDefault();
      const factor = wheelFactor(e.deltaY, e.deltaMode, e.ctrlKey);
      const p = centreOf(e.clientX, e.clientY);
      measure();
      zoom.zoomAt(zoom.scale * factor, p.x, p.y);
      animate = false;
      scheduleSnap();
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  $effect(() => {
    return () => {
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      if (snapTimer !== null) { clearTimeout(snapTimer); snapTimer = null; }
    };
  });

  function onClick(e: MouseEvent): void {
    if (swallowClick) { swallowClick = false; return; }
    if (!imgEl || imgEl.naturalWidth <= 0) return;
    const pt = e.detail === 0 ? { x: 0, y: 0 } : centreOf(e.clientX, e.clientY);
    measure();
    zoom.toggleAt(pt.x, pt.y);
    animate = true;
    setTimeout(() => (animate = false), 150);
  }

  function onClickCapture(e: MouseEvent): void {
    if (swallowClick) {
      e.stopPropagation();
      e.preventDefault();
      swallowClick = false;
    }
  }

  function onPointerDown(e: PointerEvent): void {
    if (!zoom.active) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    activePointers.add(e.pointerId);
    if (activePointers.size > 1) { drag = null; return; }
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false };
    pendingDx = 0;
    pendingDy = 0;
    last = { x: e.clientX, y: e.clientY };
    try { stageEl?.setPointerCapture?.(e.pointerId); } catch { /* noop */ }
    gesture = true;
  }

  function onPointerMove(e: PointerEvent): void {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) > 4) drag.moved = true;
    if (drag.moved && last) {
      pendingDx += e.clientX - last.x;
      pendingDy += e.clientY - last.y;
      last = { x: e.clientX, y: e.clientY };
      if (!rafId) {
        rafId = requestAnimationFrame(() => {
          rafId = 0;
          if (pendingDx !== 0 || pendingDy !== 0) {
            zoom.panBy(pendingDx, pendingDy);
            pendingDx = 0;
            pendingDy = 0;
          }
        });
      }
    }
  }

  function onPointerUp(e: PointerEvent): void {
    activePointers.delete(e.pointerId);
    if (drag?.moved) {
      swallowClick = true;
      setTimeout(() => (swallowClick = false), 0);
    }
    flushPan();
    drag = null;
    gesture = false;
  }

  function onPointerCancel(e: PointerEvent): void {
    activePointers.delete(e.pointerId);
    flushPan();
    drag = null;
    gesture = false;
  }

  function flushPan(): void {
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    if (pendingDx !== 0 || pendingDy !== 0) {
      zoom.panBy(pendingDx, pendingDy);
      pendingDx = 0;
      pendingDy = 0;
    }
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
  class:zoomed={zoom.active}
  class:panning={gesture}
  bind:this={stageEl}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointercancel={onPointerCancel}
  onclickcapture={onClickCapture}
>
  <button
    type="button"
    class="imgbtn"
    aria-label={zoom.active ? "Fit to screen" : "Actual size"}
    onclick={onClick}
  >
    <img
      bind:this={imgEl}
      {src}
      {alt}
      class:zoomed={zoom.active}
      class:animate={animate}
      style={zoom.active ? `transform: translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale});` : undefined}
      onload={measure}
    />
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
    touch-action: none;
    user-select: none;
  }
  .stage.zoomed {
    overflow: hidden;
    cursor: grab;
  }
  .stage.zoomed.panning {
    cursor: grabbing;
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
    transform-origin: center center;
    flex: none;
  }
  .stage.panning img.zoomed {
    will-change: transform;
  }
  img.zoomed.animate {
    transition: transform 120ms ease-out;
  }
  @media (prefers-reduced-motion: reduce) {
    img.zoomed.animate {
      transition: none;
    }
  }
</style>
