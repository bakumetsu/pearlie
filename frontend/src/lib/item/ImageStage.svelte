<script lang="ts">
  import { SvelteMap } from "svelte/reactivity";
  import { wheelFactor, type Zoom } from "./zoomModel.svelte";
  import ZoomControls from "./ZoomControls.svelte";

  let { src, alt, preload = null, zoom, disabled = false }: {
    src: string;
    alt: string;
    preload?: string | null;
    zoom: Zoom;
    disabled?: boolean;
  } = $props();

  let stageEl: HTMLDivElement | undefined = $state();
  let imgEl: HTMLImageElement | undefined = $state();
  let imgBtn: HTMLButtonElement | undefined = $state();
  let gesture = $state(false);
  let animate = $state(false);
  let swallowClick = false;

  let drag: { id: number; x: number; y: number; moved: boolean } | null = null;
  const pointers = new SvelteMap<number, { x: number; y: number }>();
  let pinch: { dist: number; mx: number; my: number } | null = null;
  let lastNatW = 0;
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

  function onLoad(): void {
    const n = imgEl?.naturalWidth ?? 0;
    if (zoom.active && lastNatW > 0 && n > 0 && lastNatW !== n) zoom.rescale(lastNatW / n);
    if (n > 0) lastNatW = n;
    measure();
  }

  function centreOf(clientX: number, clientY: number): { x: number; y: number } {
    const rect = stageEl!.getBoundingClientRect();
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  }

  function pinchGeometry(): { dist: number; mx: number; my: number } | null {
    const entries = [...pointers.entries()].slice(0, 2);
    if (entries.length < 2) return null;
    const [a, b] = [entries[0][1], entries[1][1]];
    return {
      dist: Math.hypot(b.x - a.x, b.y - a.y),
      mx: (a.x + b.x) / 2,
      my: (a.y + b.y) / 2,
    };
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
      if (disabled) return;
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
    if (disabled) return;
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
    if (disabled) return;
    if (e.target instanceof Element && e.target.closest("[data-zoombar]")) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) {
      flushPan();
      drag = null;
      pinch = pinchGeometry();
      gesture = true;
      return;
    }
    if (pointers.size > 2) return;
    if (!zoom.active) return;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false };
    pendingDx = 0;
    pendingDy = 0;
    last = { x: e.clientX, y: e.clientY };
    try { stageEl?.setPointerCapture?.(e.pointerId); } catch { /* noop */ }
    gesture = true;
  }

  function onPointerMove(e: PointerEvent): void {
    if (pointers.has(e.pointerId)) {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }
    if (pinch && pointers.size >= 2) {
      const g = pinchGeometry();
      if (g && pinch.dist > 0) {
        measure();
        const p = centreOf(pinch.mx, pinch.my);
        zoom.zoomAt(zoom.scale * (g.dist / pinch.dist), p.x, p.y);
        zoom.panBy(g.mx - pinch.mx, g.my - pinch.my);
      }
      pinch = g;
      animate = false;
      return;
    }
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
    pointers.delete(e.pointerId);
    if (pinch !== null) {
      if (pointers.size < 2) {
        pinch = null;
        swallowClick = true;
        setTimeout(() => (swallowClick = false), 0);
        scheduleSnap();
      }
      if (pointers.size === 1 && zoom.active) {
        const [id, pos] = [...pointers.entries()][0];
        drag = { id, x: pos.x, y: pos.y, moved: true };
        last = { x: pos.x, y: pos.y };
        pendingDx = 0;
        pendingDy = 0;
        gesture = true;
        return;
      }
      flushPan();
      drag = null;
      gesture = false;
      return;
    }
    if (drag?.moved) {
      swallowClick = true;
      setTimeout(() => (swallowClick = false), 0);
    }
    flushPan();
    drag = null;
    gesture = false;
  }

  function onPointerCancel(e: PointerEvent): void {
    pointers.delete(e.pointerId);
    if (pinch !== null) {
      if (pointers.size < 2) {
        pinch = null;
        swallowClick = true;
        setTimeout(() => (swallowClick = false), 0);
        scheduleSnap();
      }
      if (pointers.size === 1 && zoom.active) {
        const [id, pos] = [...pointers.entries()][0];
        drag = { id, x: pos.x, y: pos.y, moved: true };
        last = { x: pos.x, y: pos.y };
        pendingDx = 0;
        pendingDy = 0;
        gesture = true;
        return;
      }
      flushPan();
      drag = null;
      gesture = false;
      return;
    }
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
    aria-label={zoom.active ? "Fit to screen" : "Zoom in here"}
    bind:this={imgBtn}
    onclick={onClick}
  >
    <img
      bind:this={imgEl}
      {src}
      {alt}
      class:zoomed={zoom.active}
      class:animate={animate}
      style={zoom.active ? `transform: translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale});` : undefined}
      onload={onLoad}
    />
  </button>
  {#if !disabled}
    <ZoomControls {zoom} onhide={() => imgBtn?.focus()} />
  {/if}
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
