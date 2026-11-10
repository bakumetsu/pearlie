<!-- WallOverlay: dark image viewer layer over the Wall/Masonry grid (T-65 core) -->
<script lang="ts">
  import { onMount, untrack } from "svelte";
  import type { Api, LibraryItem } from "../api/client";
  import { keyOf } from "../stores/shared.svelte";
  import { createItemView } from "../item/itemView.svelte";
  import type { GridLike, ToastsLike } from "../item/itemView.svelte";
  import { canStep, stepInList, type ListGrid } from "../item/listNav";
  import ImageStage from "../item/ImageStage.svelte";
  import Icon from "../components/Icon.svelte";
  import { pageOptions, rangeText, clampInput } from "./pager";
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
    onpage,
  }: {
    id: string;
    grid: OverlayGrid;
    perPage: number;
    api: Api;
    toasts: ToastsLike;
    onstep: (id: string) => void;
    onclose: () => void;
    onpage: (page: number) => void;
  } = $props();

  let layerEl: HTMLDivElement | undefined = $state();
  let closeEl: HTMLButtonElement | undefined = $state();
  let zoomed = $state(false);
  let stepping = $state(false);
  let fieldText = $state("");

  // svelte-ignore state_referenced_locally
  // grid, api and toasts are fixed for the lifetime of the overlay
  const view = createItemView({ api, grid, toasts });

  $effect(() => {
    const i = id;
    untrack(() => {
      void view.load("images", i);
      zoomed = false;
    });
  });

  $effect(() => {
    const p = grid.page;
    fieldText = String(p);
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

  const name = $derived(
    view.detail?.file_name ??
      view.detail?.title ??
      current?.file_name ??
      current?.title ??
      ""
  );

  const busy = $derived(view.status === "loading" || stepping);

  const canPrev = $derived(canStep(grid, key, -1, { cross: true, kind: "image" }));
  const canNext = $derived(canStep(grid, key, 1, { cross: true, kind: "image" }));

  const pageOpts = $derived(grid.pages !== null ? pageOptions(grid.pages) : null);

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
    zoomed = !zoomed;
  }

  const canRate = $derived(view.status === "ready" && view.detail?.id === id);

  function rate(n: number) {
    if (!canRate) return;
    void view.setRating(n);
  }

  const detailsHref = $derived(itemHref({ kind: "image", id }));

  async function step(dir: 1 | -1) {
    if (stepping) return;
    if (!canStep(grid, key, dir, { cross: true, kind: "image" })) return;
    stepping = true;
    try {
      const t = await stepInList(grid, key, dir, { cross: true, kind: "image" });
      if (t) {
        onstep(t.id);
      } else {
        toasts.push({ kind: "error", message: "Could not load the next page" });
      }
    } finally {
      stepping = false;
    }
  }

  function commitPageField() {
    if (grid.pages === null) return;
    const next = clampInput(fieldText, grid.pages);
    if (next !== null && next !== grid.page) {
      fieldText = String(next);
      onpage(next);
    } else {
      fieldText = String(grid.page);
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
      else onclose();
    } else if (e.key === "z") {
      e.preventDefault();
      e.stopPropagation();
      toggleZoom();
    } else if (/^[1-5]$/.test(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      rate(Number(e.key));
    }
  }

  function onLayerClick(e: MouseEvent) {
    if (
      e.target === e.currentTarget ||
      (e.target as HTMLElement).classList.contains("stage")
    ) {
      onclose();
    }
  }

  onMount(() => {
    closeEl?.focus();
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
      onclick={onclose}
      bind:this={closeEl}
    >
      <Icon name="x" size={24} />
    </button>
    <div class="page-area">
      {#if grid.pages !== null}
        {#if pageOpts !== null && pageOpts.kind === "select"}
          <select
            class="page-select"
            aria-label="Page"
            value={grid.page}
            onchange={(e) => onpage(Number(e.currentTarget.value))}
          >
            {#each pageOpts.values as n (n)}
              <option value={n}>{n} / {grid.pages}</option>
            {/each}
          </select>
        {:else if pageOpts !== null && pageOpts.kind === "field"}
          <input
            class="page-field"
            aria-label="Page"
            inputmode="numeric"
            bind:value={fieldText}
            onkeydown={(e) => {
              if (e.key === "Enter") commitPageField();
            }}
            onblur={commitPageField}
          />
          <span class="muted">/ {grid.pages}</span>
        {/if}
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
    <div class="stage-wrap" aria-busy={busy}>
      {#if view.status === "gone" || view.status === "error"}
        <p class="msg" role="status">Could not load this image.</p>
      {:else if imageSrc}
        <ImageStage src={imageSrc} alt={name} preload={null} bind:zoomed />
      {/if}
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
    <div class="bar-right"><button type="button" class="act" aria-label="Zoom" aria-pressed={zoomed} onclick={toggleZoom}><Icon name={zoomed ? "zoom-out" : "zoom-in"} size={22} /></button><a class="act" href={detailsHref} aria-label="Details"><Icon name="info" size={22} /></a></div>
    <!-- bar-right: action group (zoom, details, trash); room for a favourite heart between zoom and details -->
  </div>
</div>

<style>
  .layer {
    position: fixed;
    inset: 0;
    z-index: 950;
    background: rgba(0, 0, 0, 0.82);
    backdrop-filter: blur(12px);
    color: #fff;
    display: flex;
    flex-direction: column;
    outline: none;
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

  .page-select {
    height: 44px;
    background: transparent;
    border: none;
    color: #fff;
    border-radius: var(--r-md);
    font-size: 0.9rem;
    cursor: pointer;
  }

  .page-select option {
    color: #000;
    background: #fff;
  }

  .page-field {
    height: 44px;
    width: 4em;
    background: transparent;
    border: none;
    color: #fff;
    border-radius: var(--r-md);
    font-size: 0.9rem;
    text-align: center;
  }

  .page-text {
    font-size: 0.9rem;
  }

  .muted {
    color: rgba(255, 255, 255, 0.6);
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

  .msg {
    color: rgba(255, 255, 255, 0.7);
    font-size: 0.95rem;
    margin: 0;
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
    color: inherit;
    cursor: pointer;
    text-decoration: none;
  }

  .act[aria-pressed="true"] {
    background: rgba(255, 255, 255, 0.15);
    border-radius: var(--r-md);
  }

  .bar-left :global(button) {
    min-width: 44px;
    min-height: 44px;
  }

  button:focus-visible,
  select:focus-visible,
  input:focus-visible {
    outline: 2px solid #fff;
    outline-offset: 2px;
  }
</style>
