<script lang="ts">
  import { untrack } from "svelte";
  import type { Match } from "../lib/router";
  import type { LibraryItem } from "../lib/api/client";
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { toPlural, toSingular, itemHref } from "../lib/item/kinds";
  import { createItemView } from "../lib/item/itemView.svelte";
  import { seeAllGrid, keyOf } from "../lib/stores/shared.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { player } from "../lib/player/player.svelte";
  import StageSlot from "../lib/player/StageSlot.svelte";
  import ImageStage from "../lib/item/ImageStage.svelte";
  import ItemPanel from "../lib/item/ItemPanel.svelte";
  import SeriesGrid from "../lib/item/SeriesGrid.svelte";
  import { rejectTag } from "../lib/item/reject";
  import Icon from "../lib/components/Icon.svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const view = createItemView({ api, grid: seeAllGrid, toasts });

  let zoomed = $state(false);
  let lastNav = 0;

  const kind = $derived(toPlural(match.params.kinds ?? ""));
  const id = $derived(match.params.id ?? "");

  $effect(() => {
    if (kind !== null) {
      zoomed = false;
      void view.load(kind, id);
    }
  });

  $effect(() => {
    const d = view.detail;
    const stream = d?.kind === "video" ? d.stream_url : null;
    if (d && stream) {
      untrack(() => {
        player.open({
          id: d.id,
          title: d.title,
          streamUrl: stream,
          posterUrl: d.thumb_url,
          fallbacks: d?.kind === "video" ? d.fallback_streams ?? [] : [],
          href: itemHref(d),
        });
      });
    }
  });

  const idx = $derived(
    kind !== null
      ? seeAllGrid.items.findIndex((t) => keyOf(t) === toSingular(kind) + ":" + id)
      : -1,
  );
  const hasList = $derived(idx >= 0);

  function nearestLibrary(fromIdx: number, dir: 1 | -1): LibraryItem | null {
    const items = seeAllGrid.items;
    let i = fromIdx + dir;
    while (i >= 0 && i < items.length) {
      const item = items[i]!;
      if (!("post_id" in item)) return item as LibraryItem;
      i += dir;
    }
    return null;
  }

  const prev = $derived(hasList ? nearestLibrary(idx, -1) : null);
  const next = $derived(hasList ? nearestLibrary(idx, 1) : null);

  const preload = $derived(
    next?.kind === "image" ? ((next as { full_url?: string }).full_url ?? null) : null,
  );

  function goNext(): void {
    lastNav = Date.now();
    if (next) {
      router.navigate(itemHref(next));
      return;
    }
    if (seeAllGrid.hasMore) {
      void (async () => {
        await seeAllGrid.loadMore();
        const items = seeAllGrid.items;
        const i = kind !== null
          ? items.findIndex((t) => keyOf(t) === toSingular(kind) + ":" + id)
          : -1;
        if (i >= 0) {
          for (let j = i + 1; j < items.length; j++) {
            const item = items[j]!;
            if (!("post_id" in item)) {
              router.navigate(itemHref(item as LibraryItem));
              return;
            }
          }
        }
      })();
    }
  }

  function goPrev(): void {
    lastNav = Date.now();
    if (prev) {
      router.navigate(itemHref(prev));
    }
  }

  function back(): void {
    if (history.length > 1) {
      history.back();
    } else {
      router.navigate("/library");
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
      case "z":
      case "Z":
        if (view.detail?.kind === "image") zoomed = !zoomed;
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
</script>

<svelte:window onkeydown={onKey} />

<div class="item">
  <header class="bar">
    <button class="bar-btn" aria-label="Back" onclick={back}>
      <Icon name="arrow-left" />
    </button>
    <h1 class="bar-title">{view.detail?.title ?? "\u2026"}</h1>
    {#if hasList}
      <button class="bar-btn" aria-label="Previous item" disabled={!prev} onclick={goPrev}>
        <Icon name="chevron-left" />
      </button>
      <button class="bar-btn" aria-label="Next item" disabled={!next} onclick={goNext}>
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

  <div class="body" onwheel={onWheel}>
    {#if kind === null || view.status === "gone"}
      <div class="state">
        <p>This item is gone</p>
        <button onclick={back}>Back</button>
      </div>
    {:else if view.status === "loading"}
      <div class="stage" aria-busy="true"><div class="skel"></div></div>
      <aside class="panel" aria-busy="true"><div class="skel"></div></aside>
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
            bind:zoomed
          />
        {:else if view.detail.kind === "video"}
          <StageSlot id={view.detail.id} />
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
      <aside class="panel">
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
  }

  .stage {
    background: #000;
    min-height: 320px;
    display: grid;
    place-items: center;
    overflow: hidden;
  }

  .notice { margin: 0 0 var(--s-2); font-size: 0.875rem; color: var(--muted); }

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
