<script lang="ts">
  import { untrack } from "svelte";
  import Tile from "../components/Tile.svelte";
  import type { LibraryItem, WebItem } from "../api/client";
  import { itemHref } from "../item/kinds";
  import { webItemHref } from "../router";
  import { keyOf } from "../stores/shared.svelte";
  import type { Mode } from "./layout";
  import { zoomSize, columnCount, dealMasonry, wallRows } from "./layout";
  import { itemAspect, captionLines } from "./sources";
  import { VirtualLayout, WALL_GAP, MASONRY_GAP } from "./virtualLayout";

  type Item = LibraryItem | WebItem;
  interface Cell {
    index: number;
    key: string;
    item: Item;
    x: number;
    y: number;
    w: number;
    h: number;
  }

  let {
    items,
    mode,
    zoom,
    loading,
    skeletons,
    saveStates,
    onsave,
    onnavigate,
    onopenitem,
    onopenweb,
    webHref,
    landscape = false,
  }: {
    items: Item[];
    mode: Mode;
    zoom: number;
    loading: boolean;
    skeletons: number;
    saveStates: Record<string, "queued" | "in_library">;
    onsave: (item: WebItem) => void;
    onnavigate: (e: MouseEvent) => void;
    onopenitem?: (item: LibraryItem) => void;
    onopenweb?: (item: WebItem) => void;
    webHref?: (item: WebItem) => string | undefined;
    landscape?: boolean;
  } = $props();

  // Until the width is known (first paint, jsdom) the first FLOW_COUNT items render in normal flow.
  const FLOW_COUNT = 48;

  let el = $state<HTMLElement>();
  let width = $state(0);

  // 16:9 video cells are wider, so a row holds 4-5.
  const size = $derived(zoomSize(mode, zoom) * (landscape && mode === "grid" ? 1.6 : 1));

  // ---- unmeasured-width fallback: today's flow layout over the first items ----
  const flowItems = $derived(items.slice(0, FLOW_COUNT));
  const flowAspects = $derived(flowItems.map(itemAspect));
  const flowRows = $derived(wallRows(flowAspects, width, size, WALL_GAP));
  const flowDealt = $derived(dealMasonry(flowAspects, columnCount(width, size, MASONRY_GAP)));

  // ---- windowed layout ----
  const layout = new VirtualLayout();
  let built = $state(false);
  let total = $state(0);
  let count = $state(0);
  let placed = $state.raw<Cell[]>([]);
  let layoutSig = "";
  let lastKey: string | undefined;
  let firstKey: string | undefined;
  // Caption metrics measured from a rendered tile; bumping `metricsVer` rebuilds the layout.
  let metricsVer = $state(0);
  let winSig = "";
  let ver = 0;

  function linesOf(item: Item): number {
    return mode === "grid" || mode === "list" ? captionLines(item, mode) : 0;
  }

  // Build or extend the layout. An append (the old last item is unchanged) costs O(new items).
  $effect(() => {
    const w = width;
    const sig = `${mode}|${w}|${size}|${landscape}|${metricsVer}`;
    const list = items;
    const n = list.length;
    const tail = n > 0 ? keyOf(list[n - 1]) : undefined;
    const head = n > 0 ? keyOf(list[0]) : undefined;
    if (loading || w <= 0) {
      untrack(() => {
        built = false;
        placed = [];
        winSig = "";
        layoutSig = "";
      });
      return;
    }
    untrack(() => {
      const have = layout.count;
      const same = built && sig === layoutSig;
      if (same && have > 0 && n > have && head === firstKey && keyOf(list[have - 1]) === lastKey) {
        const fresh = list.slice(have);
        layout.append(fresh.map(itemAspect), { lines: fresh.map(linesOf), keys: fresh.map(keyOf) });
      } else if (!(same && n === have && tail === lastKey && head === firstKey)) {
        layout.reset(mode, w, size, list.map(itemAspect), { lines: list.map(linesOf), keys: list.map(keyOf) });
      }
      layoutSig = sig;
      lastKey = tail;
      firstKey = head;
      built = true;
      ver++;
      total = layout.total;
      count = layout.count;
      computeWindow();
    });
  });

  // The rendered range changes only when its first or last index (or the layout) changes.
  function computeWindow() {
    if (!built || !el) return;
    const top = -el.getBoundingClientRect().top;
    const vh = window.innerHeight || 800;
    const buf = Math.max(1.5 * vh, 800);
    const list = layout.range(top - buf, top + vh + buf);
    const sig = `${ver}:${list.length}:${list[0]?.index}:${list[list.length - 1]?.index}`;
    if (sig === winSig) return;
    winSig = sig;
    const cells: Cell[] = [];
    for (const p of list) {
      const item = items[p.index];
      if (item) cells.push({ index: p.index, key: layout.keyAt(p.index) ?? keyOf(item), item, ...p.rect });
    }
    placed = cells;
  }

  // ---- aspect fix-up: a tile on screen never moves; its fix waits until it has left the screen ----
  // Not rendered, so plain (non-reactive) state is right.
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  const pending = new Map<string, number>();

  function reportAspect(key: string, aspect: number) {
    pending.set(key, aspect);
    schedule();
  }

  function flushFixups() {
    if (pending.size === 0 || !built || !el) return;
    const top = -el.getBoundingClientRect().top;
    const bottom = top + (window.innerHeight || 800);
    const anchor = layout.range(top, bottom)[0];
    const anchorKey = anchor ? layout.keyAt(anchor.index) : undefined;
    const y0 = anchor?.rect.y ?? 0;
    let applied = false;
    for (const [key, aspect] of [...pending]) {
      const i = layout.indexOf(key);
      const r = i >= 0 ? layout.rect(i) : undefined;
      if (!r) {
        pending.delete(key);
        continue;
      }
      if (r.y + r.h > top && r.y < bottom) continue;
      layout.applyAspect(i, aspect);
      pending.delete(key);
      applied = true;
    }
    if (!applied) return;
    ver++;
    total = layout.total;
    // Keep the first visible tile where it was when the change happened above it.
    const j = anchorKey ? layout.indexOf(anchorKey) : -1;
    const y1 = j >= 0 ? layout.rect(j)?.y : undefined;
    if (y1 !== undefined && y1 !== y0) window.scrollBy?.(0, y1 - y0);
  }

  // ---- caption metrics: measured once from one rendered caption, again when the zoom changes ----
  let capNode: Element | null = null;
  let capRo: ResizeObserver | null = null;

  function measureCaption() {
    const node = el?.querySelector(".vcell .title") ?? null;
    if (node !== capNode) {
      capRo?.unobserve(capNode as Element);
      capNode = node;
      if (node) capRo?.observe(node);
    }
    if (!node) return;
    const lineH = node.getBoundingClientRect().height;
    const pad = parseFloat(getComputedStyle(node).marginTop) || 0;
    if (!(lineH > 0)) return;
    const cur = layout.options;
    if (Math.abs(cur.lineH - lineH) < 0.5 && (mode === "list" || Math.abs(cur.pad - pad) < 0.5)) return;
    layout.setOptions(mode === "list" ? { lineH } : { lineH, pad });
    untrack(() => metricsVer++);
  }

  $effect(() => {
    void placed;
    void size;
    capRo ??= typeof ResizeObserver === "function" ? new ResizeObserver(() => measureCaption()) : null;
    measureCaption();
  });

  $effect(() => () => {
    capRo?.disconnect();
    capRo = null;
    capNode = null;
  });

  // ---- measuring and scrolling: one rAF per burst of scroll, resize and fix-up events ----
  let raf = 0;
  function schedule() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      flushFixups();
      computeWindow();
    });
  }

  $effect(() => {
    const node = el;
    if (!node) return;
    const read = () => (width = node.clientWidth);
    read();
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(read) : null;
    ro?.observe(node);
    return () => ro?.disconnect();
  });

  $effect(() => {
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };
  });

  const fixedH = $derived(mode === "wall" || mode === "masonry" || mode === "list");
</script>

<div class="rg" bind:this={el} style:--list-thumb="{size}px">
  {#if loading}
    {#if mode === "list"}
      <div class="list">
        {#each Array.from({ length: skeletons }, (_u, n) => n) as i (i)}
          <div class="skeleton sk-bar"></div>
        {/each}
      </div>
    {:else}
      <div class="grid" style:--cell="{size}px">
        {#each Array.from({ length: skeletons }, (_u, n) => n) as i (i)}
          <div class="skeleton sk-thumb"></div>
        {/each}
      </div>
    {/if}
  {:else if built}
    <div class="vwin" role="list" style:height="{total}px">
      {#each placed as p (p.key)}
        <div
          class="vcell {mode}"
          role="listitem"
          aria-posinset={p.index + 1}
          aria-setsize={count}
          style:transform="translate({p.x}px, {p.y}px)"
          style:width="{p.w}px"
          style:height={fixedH ? `${p.h}px` : undefined}
        >
          {@render tile(p.item, mode, mode === "wall" || mode === "masonry" ? p.w / p.h : undefined, p.key)}
        </div>
      {/each}
    </div>
  {:else if mode === "grid"}
    <div class="grid" style:--cell="{size}px">
      {#each flowItems as item (keyOf(item))}
        {@render tile(item, "grid", undefined)}
      {/each}
    </div>
  {:else if mode === "list"}
    <div class="list">
      {#each flowItems as item (keyOf(item))}
        {@render tile(item, "list", undefined)}
      {/each}
    </div>
  {:else if mode === "wall"}
    {#each flowRows as row, r (r)}
      <div class="wall-row">
        {#each row as i (i)}
          <div class="wall-cell" style:flex="{flowAspects[i]} 1 0%">
            {@render tile(flowItems[i], "wall", flowAspects[i])}
          </div>
        {/each}
      </div>
    {/each}
  {:else}
    <div class="masonry">
      {#each flowDealt as col, c (c)}
        <div class="mcol">
          {#each col as i (i)}
            {@render tile(flowItems[i], "masonry", flowAspects[i])}
          {/each}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#snippet tile(item: Item, variant: Mode, aspect: number | undefined, key?: string)}
  {#if "post_id" in item}
    <Tile
      item={item as WebItem}
      variant={variant}
      aspect={aspect}
      onaspect={key !== undefined && aspect !== undefined ? (a) => reportAspect(key, a) : undefined}
      href={webItemHref((item as WebItem).source, (item as WebItem).post_id) ?? webHref?.(item as WebItem)}
      saveState={saveStates[(item as WebItem).source + ":" + (item as WebItem).post_id] ?? "idle"}
      onsave={() => onsave(item as WebItem)}
      onopen={onopenweb ? () => onopenweb(item as WebItem) : undefined}
    />
  {:else}
    <Tile
      item={item as LibraryItem}
      variant={variant}
      aspect={aspect}
      onaspect={key !== undefined && aspect !== undefined ? (a) => reportAspect(key, a) : undefined}
      landscape={landscape}
      href={itemHref(item as LibraryItem)}
      onnavigate={onnavigate}
      onopenitem={onopenitem}
    />
  {/if}
{/snippet}

<style>
  .rg {
    display: block;
    width: 100%;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--cell), 1fr));
    gap: 16px;
  }

  .list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .list > :global(*) {
    border-bottom: 1px solid var(--border, rgba(127, 127, 127, 0.25));
  }

  .vwin {
    position: relative;
    overflow-anchor: none;
  }

  .vcell {
    position: absolute;
    top: 0;
    left: 0;
    box-sizing: border-box;
  }

  .vcell.list {
    border-bottom: 1px solid var(--border, rgba(127, 127, 127, 0.25));
  }

  .wall-row {
    display: flex;
    gap: 2px;
    margin-bottom: 2px;
  }

  .wall-cell {
    min-width: 0;
  }

  .masonry {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }

  .mcol {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .skeleton {
    background: var(--surface);
    border-radius: var(--r-md);
  }

  .sk-thumb {
    aspect-ratio: 3 / 4;
  }

  .sk-bar {
    height: 56px;
  }
</style>
