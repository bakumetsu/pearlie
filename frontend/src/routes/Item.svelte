<script lang="ts">
  import { untrack, tick } from "svelte";
  import type { Match } from "../lib/router";
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { toPlural, toSingular, itemHref } from "../lib/item/kinds";
  import { nearestInList, canStep, stepInList } from "../lib/item/listNav";
  import { createItemView } from "../lib/item/itemView.svelte";
  import { gridFor, keyOf } from "../lib/stores/shared.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { player } from "../lib/player/player.svelte";
  import { toPlayerItem } from "../lib/player/playerNav.svelte";
  import StageSlot from "../lib/player/StageSlot.svelte";
  import ImageStage from "../lib/item/ImageStage.svelte";
  import { createZoom, zoomKey } from "../lib/item/zoomModel.svelte";
  import ItemPanel from "../lib/item/ItemPanel.svelte";
  import SeriesGrid from "../lib/item/SeriesGrid.svelte";
  import { rejectTag } from "../lib/item/reject";
  import { PHONE_MAX, initialOpen, savePanel } from "../lib/item/panelState";
  import Icon from "../lib/components/Icon.svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const view = createItemView({ api, grid: () => grid, toasts });

  const zoom = createZoom();
  let lastNav = 0;

  let vw = $state(window.innerWidth);
  const phone = $derived(vw < PHONE_MAX);
  let panelOpen = $state(initialOpen(window.innerWidth));
  let panelEl = $state<HTMLElement | null>(null);
  let handleEl = $state<HTMLButtonElement | null>(null);
  let closeEl = $state<HTMLButtonElement | null>(null);

  const kind = $derived(toPlural(match.params.kinds ?? ""));
  const id = $derived(match.params.id ?? "");
  const grid = $derived(gridFor(kind));

  $effect(() => {
    if (kind !== null) {
      untrack(() => zoom.reset());
      void view.load(kind, id);
    }
  });

  $effect(() => {
    const d = view.detail;
    const stream = d?.kind === "video" ? d.stream_url : null;
    if (d && stream) {
      untrack(() => {
        const pi = toPlayerItem(d);
        if (pi) player.open(pi);
      });
    }
  });

  const idx = $derived(
    kind !== null
      ? grid.items.findIndex((t) => keyOf(t) === toSingular(kind) + ":" + id)
      : -1,
  );
  const hasList = $derived(idx >= 0);
  const hasPanel = $derived(kind !== null && (view.status === "loading" || (view.status === "ready" && !!view.detail)));

  const key = $derived(kind !== null ? toSingular(kind) + ":" + id : "");

  const prev = $derived(hasList ? nearestInList(grid.items, idx, -1) : null);
  const next = $derived(hasList ? nearestInList(grid.items, idx, 1) : null);

  const canPrev = $derived(hasList && canStep(grid, key, -1, { cross: true }));
  const canNext = $derived(hasList && canStep(grid, key, 1, { cross: true }));

  const preload = $derived(
    next?.kind === "image" ? ((next as { full_url?: string }).full_url ?? null) : null,
  );

  function goNext(): void {
    lastNav = Date.now();
    if (next) {
      router.navigate(itemHref(next), { replace: true });
      return;
    }
    void stepInList(grid, key, 1, { cross: true }).then((t) => {
      if (t) router.navigate(itemHref(t), { replace: true });
    });
  }

  function goPrev(): void {
    lastNav = Date.now();
    if (prev) {
      router.navigate(itemHref(prev), { replace: true });
      return;
    }
    void stepInList(grid, key, -1, { cross: true }).then((t) => {
      if (t) router.navigate(itemHref(t), { replace: true });
    });
  }

  function back(): void {
    if (router.canGoBack()) {
      history.back();
    } else {
      router.navigate("/library", { replace: true });
    }
  }

  async function onDelete(): Promise<void> {
    const target = next ?? prev;
    await view.remove();
    if (view.status === "gone") {
      if (target) {
        router.navigate(itemHref(target), { replace: true });
      } else {
        back();
      }
    }
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === "Escape" && phone && panelOpen && panelEl && e.target instanceof Node && panelEl.contains(e.target)) {
      e.preventDefault();
      void togglePanel();
      return;
    }
    const el = e.target as HTMLElement | null;
    if (
      el &&
      (el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el instanceof HTMLSelectElement ||
        el.isContentEditable)
    ) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (view.status !== "ready") return;
    if (view.detail?.kind === "image" && zoomKey(e, zoom)) return;

    switch (e.key) {
      case "Escape":
        back();
        break;
      case "f":
      case "F":
        void view.toggleFavorite();
        break;
      case "Delete":
        void onDelete();
        break;
      case " ":
        if (view.detail?.kind === "video") {
          e.preventDefault();
          player.toggle();
        }
        break;
      case "1":
      case "2":
      case "3":
      case "4":
      case "5":
        void view.setRating(Number(e.key));
        break;
      case "ArrowLeft":
        goPrev();
        break;
      case "ArrowRight":
        goNext();
        break;
    }
  }

  function onWheel(e: WheelEvent): void {
    if (
      Math.abs(e.deltaX) > 60 &&
      Math.abs(e.deltaX) > Math.abs(e.deltaY) &&
      Date.now() - lastNav > 600
    ) {
      if (e.deltaX > 0) goNext();
      else goPrev();
    }
  }

  // Handle auto-hide: true while the pointer is within 80 px of the right edge. Only a boolean is written, and only on change.
  let handleNear = $state(false);
  function onPointerMove(e: PointerEvent): void {
    const near = window.innerWidth - e.clientX <= 80;
    if (near !== handleNear) handleNear = near;
  }

  async function togglePanel(): Promise<void> {
    panelOpen = !panelOpen;
    savePanel(panelOpen);
    await tick();
    if (panelOpen) closeEl?.focus();
    else handleEl?.focus();
  }
</script>

<svelte:window onkeydown={onKey} onpointermove={onPointerMove} bind:innerWidth={vw} />

<div class="item">
  <header class="bar">
    <button class="bar-btn" aria-label="Back" onclick={back}>
      <Icon name="arrow-left" />
    </button>
    <h1 class="bar-title">{view.detail?.title ?? "\u2026"}</h1>
    {#if hasList && view.detail?.kind !== "video"}
      <button class="bar-btn" aria-label="Previous item" disabled={!canPrev} onclick={goPrev}>
        <Icon name="chevron-left" />
      </button>
      <button class="bar-btn" aria-label="Next item" disabled={!canNext} onclick={goNext}>
        <Icon name="chevron-right" />
      </button>
    {/if}
    <button
      class="bar-btn"
      aria-label="Favorite"
      aria-pressed={view.detail?.favorite ?? false}
      onclick={() => view.toggleFavorite()}
    >
      <Icon name={view.detail?.favorite ? "heart-filled" : "heart"} />
    </button>
    <button class="bar-btn" aria-label="Delete" onclick={() => void onDelete()}>
      <Icon name="trash" />
    </button>
  </header>

  <div class="body" class:phone class:collapsed={!panelOpen} onwheel={onWheel}>
    {#if kind === null || view.status === "gone"}
      <div class="state">
        <p>This item is gone</p>
        <button onclick={back}>Back</button>
      </div>
    {:else if view.status === "loading"}
      <div class="stage" aria-busy="true"><div class="skel"></div></div>
      <aside class="panel" aria-busy="true" inert={!panelOpen} aria-hidden={!panelOpen} bind:this={panelEl}>
        <button class="panel-btn" bind:this={closeEl} aria-label="Hide panel" aria-expanded={panelOpen} onclick={() => void togglePanel()}><Icon name="chevrons-right" /></button>
        <div class="skel"></div>
      </aside>
    {:else if view.status === "error"}
      <div class="state">
        <p>Could not load this item</p>
        <button onclick={() => view.load(kind!, id)}>Retry</button>
      </div>
    {:else if view.detail}
      <div class="stage">
        {#if view.detail.kind === "image"}
          <ImageStage
            src={view.detail.full_url ?? view.detail.thumb_url}
            alt={view.detail.title}
            preload={preload}
            {zoom}
          />
        {:else if view.detail.kind === "video"}
          <StageSlot id={view.detail.id} />
          {#if player.failed || view.detail.notice?.code === "streams_unavailable"}
            <p class="notice" role="status">
              This video cannot be played here.
              {#if view.detail.stash_link}
                <a class="stash-link" href={view.detail.stash_link} target="_blank" rel="noopener noreferrer">Open in Stash</a>
              {/if}
            </p>
          {/if}
        {:else if view.detail.kind === "series"}
          <div class="series">
            {#if view.detail.notice}<p class="notice" role="status">{view.detail.notice.message}</p>{/if}
            <SeriesGrid
              books={view.detail.books ?? []}
              onopen={(b) => router.navigate("/read/" + encodeURIComponent(b.id) + "?series=" + encodeURIComponent(view.detail!.id))}
            />
          </div>
        {:else if view.detail.kind === "book"}
          <div class="book-stage">
            <img src={view.detail.thumb_url} alt={view.detail.title} />
            <button onclick={() => router.navigate("/read/" + encodeURIComponent(view.detail!.id))}>
              Read
            </button>
          </div>
        {/if}
      </div>
      <aside class="panel" inert={!panelOpen} aria-hidden={!panelOpen} bind:this={panelEl}>
        <button class="panel-btn" bind:this={closeEl} aria-label="Hide panel" aria-expanded={panelOpen} onclick={() => void togglePanel()}><Icon name="chevrons-right" /></button>
        <ItemPanel
          detail={view.detail}
          tags={view.tagStrings}
          onrate={(n) => view.setRating(n)}
          onaddtag={(t) => view.addTagInput(t)}
          onremovetag={(t) => view.removeTagByName(t)}
          onrejecttag={(t) => void rejectTag(api, toasts, t)}
        />
      </aside>
    {/if}
    {#if !panelOpen && hasPanel}
      <button class="handle" class:near={handleNear} bind:this={handleEl} aria-label="Show panel" aria-expanded={panelOpen} onclick={() => void togglePanel()}><Icon name="chevrons-left" /></button>
    {/if}
  </div>
</div>

<style>
  .item {
    display: grid;
    grid-template-rows: auto 1fr;
    height: 100vh;
    font-family: inherit;
    color: var(--text);
    background: var(--bg);
  }

  .bar {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    padding: var(--s-2) var(--s-3);
    padding-right: calc(var(--s-3) + var(--sfw-inset));
    border-bottom: 1px solid var(--line);
    background: var(--surface);
  }

  .bar-btn {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: var(--s-1);
    background: transparent;
    color: var(--text);
    cursor: pointer;
  }
  .bar-btn:hover { background: var(--bg); }
  .bar-btn:disabled { opacity: 0.35; cursor: default; }

  .bar-title {
    flex: 1;
    margin: 0;
    font-size: var(--t-15);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-align: center;
  }

  .body {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 360px;
    min-height: 0;
    overflow: hidden;
    position: relative;
    transition: grid-template-columns 250ms ease;
  }

  .body.collapsed:not(.phone) {
    grid-template-columns: minmax(0, 1fr) 0px;
  }

  .body.phone {
    grid-template-columns: minmax(0, 1fr);
  }

  .stage {
    background: #000;
    min-height: 320px;
    display: grid;
    grid-template: minmax(0, 1fr) / minmax(0, 1fr);
    place-items: center;
    min-width: 0;
    overflow: hidden;
  }

  .notice { margin: 0 0 var(--s-2); font-size: 0.875rem; color: var(--muted); }
  .stash-link { display: inline-flex; align-items: center; min-height: 44px; padding: 0 var(--s-2); }

  .series {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    padding: var(--s-4);
    align-self: start;
    background: var(--bg);
  }

  .panel {
    overflow-y: auto;
    padding: var(--s-4);
    border-left: 1px solid var(--line);
    background: var(--surface);
    min-width: 0;
    transition: visibility 0s linear 0s;
  }

  .body.collapsed:not(.phone) .panel {
    visibility: hidden;
    padding-left: 0;
    padding-right: 0;
    border-left-width: 0;
    overflow: hidden;
    transition: visibility 0s linear 250ms;
  }

  .body.phone .panel {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(360px, calc(100% - 16px));
    z-index: 5;
    transform: translateX(0);
    transition: transform 250ms ease, visibility 0s linear 0s;
    box-shadow: 0 0 24px rgba(0, 0, 0, 0.4);
  }

  .body.phone.collapsed .panel {
    transform: translateX(100%);
    visibility: hidden;
    transition: transform 250ms ease, visibility 0s linear 250ms;
    pointer-events: none;
  }

  .panel-btn {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border: none;
    border-radius: var(--s-1);
    background: transparent;
    color: var(--text);
    cursor: pointer;
    margin: 0 0 var(--s-2) auto;
  }

  .handle {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border: 1px solid var(--line);
    border-right: none;
    border-radius: var(--s-1) 0 0 var(--s-1);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    position: absolute;
    top: var(--s-4);
    right: 0;
    z-index: 22;
  }

  /* Phone keeps the old mid-height spot. */
  .body.phone .handle {
    top: 50%;
    transform: translateY(-50%);
  }

  /* Hover devices: hide the handle (still focusable) unless the pointer is near the right edge or it has keyboard focus. */
  @media (hover: hover) and (pointer: fine) {
    .body:not(.phone) .handle {
      opacity: 0;
      transition: opacity 150ms ease;
    }
    .body:not(.phone) .handle.near,
    .body:not(.phone) .handle:focus-visible {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .body:not(.phone) .handle,
    .body,
    .panel,
    .body.phone .panel,
    .body.collapsed:not(.phone) .panel,
    .body.phone.collapsed .panel {
      transition: none;
    }
  }

  .state button {
    background: var(--accent-bg);
    color: var(--accent);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    padding: var(--s-2) var(--s-3);
  }

  .state {
    grid-column: 1 / -1;
    display: grid;
    place-items: center;
    gap: var(--s-3);
    padding: var(--s-5);
    text-align: center;
  }

  .skel {
    width: 100%;
    height: 100%;
    min-height: 280px;
    background: var(--muted);
    border-radius: var(--s-2);
    opacity: 0.25
;
  }
</style>
