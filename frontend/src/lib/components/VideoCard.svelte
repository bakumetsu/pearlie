<!-- Video card media and info block for library tiles (T-36) -->
<script lang="ts">
  import { onDestroy } from "svelte";
  import { videoPreview } from "../stores/videoPreview.svelte";
  import type { LibraryItem } from "../api/client";
  import Icon from "./Icon.svelte";

  let {
    item,
    variant,
    aspectRatio,
    blurred,
    meta,
    onmediaclick,
    onmediakeydown,
  }: {
    item: LibraryItem;
    variant: "grid" | "wall" | "masonry" | "list";
    aspectRatio: string;
    blurred: boolean;
    meta: string;
    onmediaclick: (e: MouseEvent) => void;
    onmediakeydown: (e: KeyboardEvent) => void;
  } = $props();

  const key = $derived(item.id);

  const canPreview = $derived(
    !!item.preview_url &&
    !(
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
  );

  let sfwOff = $state(true);
  let posterShown = $state(false);

  const sub = $derived(
    [item.studio, item.date].filter(Boolean).join(" - ")
  );

  const playing = $derived(
    videoPreview.isActive(key) && canPreview && (sfwOff || posterShown)
  );

  // --- poster data-sfw-shown observer ---
  let posterEl: HTMLImageElement | undefined = $state();

  $effect(() => {
    if (!posterEl) return;
    posterShown = posterEl.hasAttribute("data-sfw-shown");
    const obs = new MutationObserver(() => {
      posterShown = posterEl!.hasAttribute("data-sfw-shown");
    });
    obs.observe(posterEl, { attributes: true, attributeFilter: ["data-sfw-shown"] });
    return () => obs.disconnect();
  });

  // --- preview control ---
  let longPressTimer: ReturnType<typeof setTimeout> | undefined;
  let swallowCleanup: ReturnType<typeof setTimeout> | undefined;

  function refreshSfw() {
    sfwOff = document.documentElement.dataset.sfw !== "on";
  }

  function startPreview() {
    if (!canPreview) return;
    refreshSfw();
    videoPreview.start(key);
  }

  function stopPreview() {
    videoPreview.stop(key);
    if (longPressTimer !== undefined) {
      clearTimeout(longPressTimer);
      longPressTimer = undefined;
    }
  }

  function swallowClick(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
  }

  // --- pointer handlers ---
  let lastPointerType: string | null = null;
  let touchStartX = 0;
  let touchStartY = 0;

  function onPointerEnter(e: PointerEvent) {
    if (e.pointerType === "mouse" || e.pointerType === "pen") {
      startPreview();
    }
  }

  function onPointerLeave() {
    stopPreview();
  }

  function onPointerDown(e: PointerEvent) {
    lastPointerType = e.pointerType;
    if (e.pointerType === "touch") {
      touchStartX = e.clientX;
      touchStartY = e.clientY;
      longPressTimer = setTimeout(() => {
        longPressTimer = undefined;
        startPreview();
        window.addEventListener("click", swallowClick, { capture: true, once: true });
        swallowCleanup = setTimeout(() => {
          window.removeEventListener("click", swallowClick, { capture: true });
        }, 600);
      }, 500);
    }
  }

  function onPointerMove(e: PointerEvent) {
    if (e.pointerType === "touch" && longPressTimer !== undefined) {
      const dx = e.clientX - touchStartX;
      const dy = e.clientY - touchStartY;
      if (dx * dx + dy * dy > 100) {
        clearTimeout(longPressTimer);
        longPressTimer = undefined;
      }
    }
  }

  function onPointerUp() {
    if (longPressTimer !== undefined) {
      clearTimeout(longPressTimer);
      longPressTimer = undefined;
    }
    stopPreview();
  }

  function onPointerCancel() {
    if (longPressTimer !== undefined) {
      clearTimeout(longPressTimer);
      longPressTimer = undefined;
    }
    stopPreview();
  }

  function onContextMenu(e: MouseEvent) {
    if (lastPointerType === "touch") {
      e.preventDefault();
    }
  }

  // --- video muted property action ---
  function setMuted(el: HTMLVideoElement) {
    el.muted = true;
  }

  // --- scroll to stop ---
  $effect(() => {
    const handler = () => stopPreview();
    window.addEventListener("scroll", handler, { capture: true, passive: true });
    return () => window.removeEventListener("scroll", handler, { capture: true });
  });

  // --- cleanup ---
  onDestroy(() => {
    if (longPressTimer !== undefined) clearTimeout(longPressTimer);
    if (swallowCleanup !== undefined) {
      clearTimeout(swallowCleanup);
      window.removeEventListener("click", swallowClick, { capture: true });
    }
    videoPreview.stop(key);
  });

  // --- duration format (copied from Tile) ---
  function formatDuration(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    if (h > 0) {
      return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    }
    return `${m}:${String(sec).padStart(2, "0")}`;
  }


</script>

<div
  class="media"

  style:aspect-ratio={aspectRatio}
  onclick={onmediaclick}
  role="button"
  tabindex="0"
  onkeydown={onmediakeydown}
  onpointerenter={onPointerEnter}
  onpointerleave={onPointerLeave}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointercancel={onPointerCancel}
  oncontextmenu={onContextMenu}
>
  <img bind:this={posterEl} src={item.thumb_url} alt="" loading="lazy" class:blur-img={blurred} />

  {#if playing}
    <video
      use:setMuted
      src={item.preview_url}
      muted
      loop
      playsinline
      preload="none"
      autoplay
      data-sfw-shown="1"
      onerror={stopPreview}
    ></video>
  {/if}

  {#if variant !== "list" && item.height != null}
    <span class="res">{item.height >= 2160 ? "4K" : `${item.height}p`}</span>
  {/if}

  {#if variant !== "list" && item.duration_s != null}
    <span class="duration">{formatDuration(item.duration_s)}</span>
  {/if}

  {#if variant !== "list" && item.favorite}
    <span class="fav">
      <Icon name="heart-filled" size={14} />
    </span>
  {/if}

  {#if blurred}
    <div class="warn-overlay">Warn: {item.blur!.tag}</div>
  {/if}
</div>

  {#if variant === "list"}
    <div class="info">
      <div class="title">{item.title}</div>
      {#if meta}<div class="meta">{meta}</div>{/if}
    </div>
  {:else}
    <div class="title">{item.title}</div>
    {#if sub}<div class="sub">{sub}</div>{/if}
  {/if}

<style>
  .media {
    position: relative;
    overflow: hidden;
    border-radius: var(--r-md);
    background: var(--surface);
    -webkit-touch-callout: none;
    user-select: none;
    -webkit-user-select: none;
    touch-action: manipulation;
  }
  .media img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .media video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    pointer-events: none;
  }
  .blur-img {
    filter: blur(18px);
  }
  .warn-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    background: rgba(0, 0, 0, 0.45);
    color: var(--text);
    font-size: var(--t-13);
    font-weight: 600;
    border-radius: var(--r-md);
  }
  .fav {
    position: absolute;
    top: var(--s-1);
    right: var(--s-1);
    z-index: 1;
    color: var(--danger-fg);
  }
  .duration,
  .res {
    position: absolute;
    bottom: var(--s-1);
    z-index: 1;
    background: rgba(0, 0, 0, 0.7);
    color: var(--text);
    font-size: var(--t-12);
    padding: 2px var(--s-1);
    border-radius: var(--r-sm);
  }
  .duration {
    right: var(--s-1);
  }
  .res {
    left: var(--s-1);
  }
  .title {
    font-size: var(--t-13);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: var(--s-1);
    color: var(--text);
  }
  .sub {
    font-size: var(--t-12);
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .info {
    min-width: 0;
    flex: 1;
  }
  .info .title {
    margin-top: 0;
  }
  .meta {
    font-size: var(--t-12);
    color: var(--muted);
    overflow-wrap: break-word;
  }
</style>
