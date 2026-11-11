<!-- WallOverlay: dark image viewer layer over the Wall/Masonry grid (T-65 core) -->
<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import type { Api, LibraryItem } from "../api/client";
  import { keyOf } from "../stores/shared.svelte";
  import { createItemView } from "../item/itemView.svelte";
  import type { GridLike, ToastsLike } from "../item/itemView.svelte";
  import { canStep, stepInList, nearestInList, pageEdge, type ListGrid } from "../item/listNav";
  import ImageStage from "../item/ImageStage.svelte";
  import Icon from "../components/Icon.svelte";
  import { rangeText } from "./pager";
  import { swipeDir } from "./swipe";
  import RatingStars from "../item/RatingStars.svelte";
  import { itemHref } from "../item/kinds";

  type OverlayGrid = ListGrid &
    GridLike & {
      total: number | null;
      stats: { megapixels?: number | null; size_bytes?: number | null } | null;
    };

  let {
    id,
    grid,
    perPage,
    api,
    toasts,
    onstep,
    onclose,
  }: {
    id: string;
    grid: OverlayGrid;
    perPage: number;
    api: Api;
    toasts: ToastsLike;
    onstep: (id: string) => void;
    onclose: () => void;
  } = $props();

  let layerEl: HTMLDivElement | undefined = $state();
  let closeEl: HTMLButtonElement | undefined = $state();
  let zoomed = $state(false);
  let stepping = $state(false);
  let deleting = $state(false);
  let imageFailed = $state(false);
  let retryN = $state(0);
  let fullscreen = $state(false);
  const canFullscreen =
    typeof document !== "undefined" &&
    document.fullscreenEnabled === true &&
    typeof HTMLElement.prototype.requestFullscreen === "function";

  let swipeStart: { id: number; x: number; y: number } | null = null;
  let swipeHandled = false;
  const activePointers = new SvelteSet<number>();

  // svelte-ignore state_referenced_locally
  // grid, api and toasts are fixed for the lifetime of the overlay
  const view = createItemView({ api, grid, toasts });

  $effect(() => {
    const i = id;
    untrack(() => {
      void view.load("images", i);
      zoomed = false;
      imageFailed = false;
      retryN = 0;
    });
  });



  const key = $derived("image:" + id);
  const current = $derived(
    (grid.items.find((t) => keyOf(t) === key) ?? null) as LibraryItem | null
  );

  const imageSrc = $derived(
    view.status === "loading"
      ? (current?.thumb_url ?? "")
      : (view.detail?.full_url ?? view.detail?.thumb_url ?? current?.thumb_url ?? "")
  );

  const stageSrc = $derived(
    retryN > 0 && imageSrc
      ? imageSrc + (imageSrc.includes("?") ? "&" : "?") + "r=" + retryN
      : imageSrc
  );

  const name = $derived(
    view.detail?.file_name ??
      view.detail?.title ??
      current?.file_name ??
      current?.title ??
      ""
  );

  const busy = $derived(view.status === "loading" || stepping || deleting);

  const canPrev = $derived(canStep(grid, key, -1, { cross: true, kind: "image" }));
  const canNext = $derived(canStep(grid, key, 1, { cross: true, kind: "image" }));



  const range = $derived(
    rangeText({
      page: grid.page,
      perPage,
      shown: grid.items.length,
      total: grid.total,
      stats: grid.stats
        ? {
            megapixels: grid.stats.megapixels ?? null,
            size_bytes: grid.stats.size_bytes ?? null,
          }
        : null,
    })
  );

  function toggleZoom() {
    if (deleting) return;
    zoomed = !zoomed;
  }

  const canRate = $derived(view.status === "ready" && view.detail?.id === id);

  function rate(n: number) {
    if (!canRate || deleting) return;
    void view.setRating(n);
  }

  const detailsHref = $derived(itemHref({ kind: "image", id }));

  async function step(dir: 1 | -1) {
    if (stepping || deleting) return;
    if (!canStep(grid, key, dir, { cross: true, kind: "image" })) return;
    stepping = true;
    try {
      const t = await stepInList(grid, key, dir, { cross: true, kind: "image" });
      if (t) {
        onstep(t.id);
      } else {
        exitFs();
        toasts.push({ kind: "error", message: "Could not load the next page" });
      }
    } finally {
      stepping = false;
    }
  }

  function neighbourTarget() {
    const idx = grid.items.findIndex((t) => keyOf(t) === key);
    return nearestInList(grid.items, idx, 1, "image") ?? nearestInList(grid.items, idx, -1, "image");
  }

  async function stepAfterRemoval(target: ReturnType<typeof neighbourTarget>) {
    if (target) {
      onstep(target.id);
      return;
    }
    const dir: 1 | -1 = pageEdge(grid, 1) ? 1 : -1;
    if (pageEdge(grid, dir)) {
      await grid.goTo(grid.page + dir);
      if (grid.status !== "error") {
        const items = grid.items;
        const t = nearestInList(items, dir === 1 ? -1 : items.length, dir, "image");
        if (t) {
          grid.markCrossed();
          onstep(t.id);
          return;
        }
      }
      toasts.push({ kind: "error", message: "Could not load the next page" });
    }
    close();
  }

  async function onDelete() {
    if (!canRate || deleting || stepping) return;
    const target = neighbourTarget();
    exitFs();
    deleting = true;
    try {
      await view.remove();
      if (view.status !== "gone") return;
      await stepAfterRemoval(target);
    } finally {
      deleting = false;
    }
  }

  async function handleGone() {
    const target = neighbourTarget();
    grid.removeById(key);
    exitFs();
    toasts.push({ kind: "info", message: "This image is gone" });
    deleting = true;
    try {
      await stepAfterRemoval(target);
    } finally {
      deleting = false;
    }
  }

  $effect(() => {
    if (view.status === "gone" && !untrack(() => deleting)) {
      untrack(() => {
        void handleGone();
      });
    }
  });

  function retry() {
    if (view.status === "error") {
      void view.load("images", id);
    } else {
      imageFailed = false;
      retryN += 1;
    }
  }



  function onKey(e: KeyboardEvent) {
    if (e.key === "Tab") {
      const sel =
        'button:not([disabled]), select, input, a[href], [tabindex]:not([tabindex="-1"])';
      const focusable = layerEl?.querySelectorAll(sel);
      if (focusable && focusable.length > 0) {
        const first = focusable[0] as HTMLElement;
        const last = focusable[focusable.length - 1] as HTMLElement;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      } else {
        e.preventDefault();
      }
      return;
    }

    const target = e.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "SELECT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable
    )
      return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key === "ArrowLeft" || e.key === "j") {
      e.preventDefault();
      e.stopPropagation();
      step(-1);
    } else if (e.key === "ArrowRight" || e.key === "l") {
      e.preventDefault();
      e.stopPropagation();
      step(1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (zoomed) zoomed = false;
      else close();
    } else if (e.key === "z") {
      e.preventDefault();
      e.stopPropagation();
      toggleZoom();
    } else if (/^[1-5]$/.test(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      rate(Number(e.key));
    } else if (e.key === "Delete") {
      e.preventDefault();
      e.stopPropagation();
      void onDelete();
    }
  }

  function onSwipePointerDown(e: PointerEvent) {
    if (e.pointerType !== "touch") return;
    activePointers.add(e.pointerId);
    if (
      activePointers.size > 1 ||
      zoomed ||
      stepping || deleting ||
      (e.target as HTMLElement).closest("button, a, select, input") !== null
    ) {
      swipeStart = null;
    } else {
      swipeStart = { id: e.pointerId, x: e.clientX, y: e.clientY };
    }
  }

  function onSwipePointerUp(e: PointerEvent) {
    activePointers.delete(e.pointerId);
    if (swipeStart && swipeStart.id === e.pointerId) {
      const dir = swipeDir(e.clientX - swipeStart.x, e.clientY - swipeStart.y);
      swipeStart = null;
      if (dir !== null) {
        swipeHandled = true;
        setTimeout(() => {
          swipeHandled = false;
        }, 0);
        void step(dir);
      }
    }
  }

  function onSwipePointerCancel(e: PointerEvent) {
    activePointers.delete(e.pointerId);
    swipeStart = null;
  }

  function onSwipeClickGuard(e: MouseEvent) {
    if (swipeHandled) {
      swipeHandled = false;
      e.stopPropagation();
      e.preventDefault();
    }
  }

  function onLayerClick(e: MouseEvent) {
    const target = e.target as HTMLElement;
    if (
      e.target === e.currentTarget ||
      target.classList.contains("mid") ||
      target.classList.contains("stage-wrap") ||
      target.classList.contains("stage")
    ) {
      close();
    }
  }

  function exitFs() {
    if (layerEl && document.fullscreenElement === layerEl) {
      void document.exitFullscreen().catch(() => {});
    }
  }

  function close() {
    exitFs();
    onclose();
  }

  function toggleFullscreen() {
    if (!layerEl) return;
    if (document.fullscreenElement === layerEl) {
      void document.exitFullscreen().catch(() => {});
    } else {
      void layerEl.requestFullscreen().catch(() => {});
    }
  }

  function onFsChange() {
    fullscreen = layerEl != null && document.fullscreenElement === layerEl;
  }

  onMount(() => {
    closeEl?.focus();
    document.addEventListener("fullscreenchange", onFsChange);
    return () => {
      document.removeEventListener("fullscreenchange", onFsChange);
      exitFs();
    };
  });
</script>

<div
  class="layer"
  role="dialog"
  aria-modal="true"
  aria-label="Image viewer"
  tabindex="-1"
  onkeydown={onKey}
  onclick={onLayerClick}
  bind:this={layerEl}
>
  <div class="top">
    <button
      type="button"
      class="close"
      aria-label="Close"
      onclick={close}
      bind:this={closeEl}
    >
      <Icon name="x" size={24} />
    </button>
    <div class="page-area">
      {#if grid.pages !== null}
        <span class="page-text">{grid.page} / {grid.pages}</span>
      {:else}
        <span class="page-text">Page {grid.page}</span>
      {/if}
      <span class="divider" aria-hidden="true"></span>
      {#if range}
        <span class="range">{range}</span>
      {/if}
    </div>
  </div>

  <div class="mid">
    <button
      type="button"
      class="nav nav-prev"
      aria-label="Previous image"
      disabled={!canPrev}
      onclick={() => step(-1)}
    >
      <Icon name="chevron-left" size={30} />
    </button>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="stage-wrap"
      class:loading={view.status === "loading"}
      aria-busy={busy}
      onpointerdown={onSwipePointerDown}
      onpointerup={onSwipePointerUp}
      onpointercancel={onSwipePointerCancel}
      onclickcapture={onSwipeClickGuard}
      onerrorcapture={(e) => { if (e.target instanceof HTMLImageElement && view.status === "ready") imageFailed = true; }}
    >
      {#if view.status === "error" || imageFailed}
        <div class="errbox" role="alert"><p>Could not load this image</p><div class="errbtns"><button type="button" class="retry" onclick={retry}>Retry</button><a class="retry" href={detailsHref}>Open details</a></div></div>
      {:else if view.status !== "gone" && stageSrc}
        <ImageStage src={stageSrc} alt={name} preload={null} bind:zoomed />
      {/if}
      {#if view.status === "loading"}<span class="spinner" aria-hidden="true"></span>{/if}
    </div>
    <button
      type="button"
      class="nav nav-next"
      aria-label="Next image"
      disabled={!canNext}
      onclick={() => step(1)}
    >
      <Icon name="chevron-right" size={30} />
    </button>
  </div>

  <div class="bottom">
    <div class="bar-left"><RatingStars value={canRate ? (view.detail?.rating ?? null) : null} onrate={rate} /></div>
    <div class="bar-name">{name}</div>
    <div class="bar-right"><button type="button" class="act" aria-label="Zoom" aria-pressed={zoomed} onclick={toggleZoom}><Icon name={zoomed ? "zoom-out" : "zoom-in"} size={22} /></button>{#if canFullscreen}<button type="button" class="act" aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"} title={fullscreen ? "Exit fullscreen" : "Fullscreen"} aria-pressed={fullscreen} onclick={toggleFullscreen}><Icon name={fullscreen ? "minimize" : "maximize"} size={22} /></button>{/if}<a class="act" class:disabled={!canRate} href={detailsHref} aria-label="Details" aria-disabled={!canRate} tabindex={canRate ? undefined : -1} onclick={(e) => { if (!canRate) e.preventDefault(); }}><Icon name="info" size={22} /></a><button type="button" class="act danger" aria-label="Delete" disabled={!canRate || deleting} onclick={onDelete}><Icon name="trash" size={22} /></button></div>
    <!-- bar-right: action group (zoom, fullscreen, details, trash); room for a favourite heart between zoom and details -->
  </div>
</div>

<style>
  .layer {
    position: fixed;
    inset: 0;
    z-index: 950;
    background: rgba(0, 0, 0, 0.82);
    backdrop-filter: blur(12px);
    animation: overlay-fade 150ms ease-out;
    color: #fff;
    display: flex;
    flex-direction: column;
    outline: none;
  }

  @keyframes overlay-fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .layer:focus-visible {
    outline: 2px solid #fff;
    outline-offset: -2px;
  }

  .top {
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    padding: var(--s-4);
  }

  .close {
    position: absolute;
    left: var(--s-4);
    min-width: 44px;
    min-height: 44px;
    width: 44px;
    height: 44px;
    background: none;
    border: 0;
    color: inherit;
    cursor: pointer;
    display: grid;
    place-items: center;
  }

  .page-area {
    display: flex;
    align-items: center;
    gap: 8px;
  }



  .page-text {
    font-size: 0.9rem;
  }



  .divider {
    width: 1px;
    height: 18px;
    background: rgba(255, 255, 255, 0.3);
    flex-shrink: 0;
  }

  .range {
    color: rgba(255, 255, 255, 0.6);
    font-size: 0.85rem;
  }

  @media (max-width: 600px) {
    .range {
      display: none;
    }
  }

  .mid {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    min-height: 0;
  }

  .nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 56px;
    height: 56px;
    background: none;
    border: 0;
    color: inherit;
    cursor: pointer;
    display: grid;
    place-items: center;
    opacity: 0.7;
    z-index: 1;
  }

  .nav:hover:not(:disabled) {
    opacity: 1;
  }

  .nav:disabled {
    opacity: 0.3;
    cursor: default;
  }

  .nav-prev {
    left: 0;
  }

  .nav-next {
    right: 0;
  }

  .stage-wrap {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    transition: opacity 0.15s;
  }

  .stage-wrap[aria-busy="true"] {
    opacity: 0.6;
  }

  .stage-wrap.loading :global(img) {
    filter: blur(6px);
  }

  .spinner {
    position: absolute;
    width: 32px;
    height: 32px;
    border: 3px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: overlay-spin 0.8s linear infinite;
  }

  @keyframes overlay-spin {
    to { transform: rotate(360deg); }
  }

  .stage-wrap :global(.stage:not(.zoomed)) {
    touch-action: pan-y pinch-zoom;
  }

  .errbox {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--s-4);
    text-align: center;
    padding: var(--s-4);
  }

  .errbox p {
    margin: 0;
    color: rgba(255,255,255,0.8);
  }

  .errbtns {
    display: flex;
    gap: var(--s-4);
  }

  .retry {
    min-width: 44px;
    min-height: 44px;
    display: inline-grid;
    place-items: center;
    padding: 0 var(--s-4);
    background: rgba(255,255,255,0.15);
    border: 0;
    border-radius: var(--r-md);
    color: #fff;
    cursor: pointer;
    text-decoration: none;
  }

  .bottom {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    padding: var(--s-4);
  }

  .bar-name {
    text-align: center;
    font-weight: 600;
    overflow-wrap: anywhere;
    max-width: 460px;
  }

  .bar-left {
    display: flex;
    align-items: center;
    justify-self: start;
  }

  .bar-right {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--s-2);
  }

  .act {
    min-width: 44px;
    min-height: 44px;
    width: 44px;
    height: 44px;
    display: grid;
    place-items: center;
    background: none;
    border: 0;
    color: rgba(255, 255, 255, 0.75);
    border-radius: 50%;
    cursor: pointer;
    text-decoration: none;
  }

  .act[aria-pressed="true"] {
    background: rgba(255, 255, 255, 0.15);
    border-radius: var(--r-md);
  }

  .act.disabled {
    opacity: 0.4;
    pointer-events: none;
  }

  .act:hover,
  .act:focus-visible {
    color: #fff;
    background: rgba(255, 255, 255, 0.12);
  }

  .act.danger:hover,
  .act.danger:focus-visible {
    color: var(--danger-hot);
  }

  .bar-left :global(button) {
    min-width: 44px;
    min-height: 44px;
  }

  /* phone: matches PHONE_MAX = 720 in item/panelState.ts (innerWidth < 720) */
  @media (max-width: 719.98px) {
    .top, .bottom { padding-inline: var(--s-4); }
    .bottom { grid-template-columns: 1fr auto; grid-template-areas: "name name" "left right"; row-gap: var(--s-2); }
    .bar-name { grid-area: name; justify-self: center; max-width: 100%; }
    .bar-left { grid-area: left; }
    .bar-right { grid-area: right; }
    .nav { width: 44px; height: 44px; background: rgba(0, 0, 0, 0.35); border-radius: 50%; opacity: 0.8; }
    .nav-prev { left: 8px; }
    .nav-next { right: 8px; }
  }

  button:focus-visible {
    outline: 2px solid #fff;
    outline-offset: 2px;
  }
</style>
