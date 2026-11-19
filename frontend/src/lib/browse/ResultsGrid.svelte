<script lang="ts">
  import { untrack, tick } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
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
    selectable = false,
    onready,
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
    // Library tiles get the select circle (only where a SelectBar exists).
    selectable?: boolean;
    landscape?: boolean;
    onready?: () => void;
  } = $props();

  // Until the width is known (first paint, jsdom) the first FLOW_COUNT items render in normal flow.
  const FLOW_COUNT = 48;
  // While a tile has focus the window also covers this many items on each side, so Tab walks real tiles.
  const FOCUS_SPAN = 12;

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
  // The tile that has focus is always rendered; a SFW reveal outlives its tile leaving the window.
  let focusKey: string | undefined;
  const revealedKeys = new SvelteSet<string>();
  let readyFired = false;
  let ready = false;

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
        // Unmeasured width: the flow fallback is the final layout, so there is nothing to wait for.
        if (!loading) fireReady();
      });
      return;
    }
    untrack(() => {
      const have = layout.count;
      const same = built && sig === layoutSig;
      const anchor = built && !same ? takeAnchor() : null;
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
      if (anchor) tick().then(() => putAnchor(anchor));
      fireReady();
    });
  });

  function fireReady() {
    if (readyFired) return;
    readyFired = true;
    tick().then(() => {
      // The width was read after the flow case fired: the real build fires it instead.
      if (width > 0 && !built) {
        readyFired = false;
        return;
      }
      ready = true;
      onready?.();
    });
  }

  // ---- scroll anchor: the first visible item and how far its top is above the screen top ----
  interface Anchor {
    key: string;
    offset: number;
  }

  // The container top in page coordinates.
  function pageTop(): number {
    return (el?.getBoundingClientRect().top ?? 0) + (window.scrollY || 0);
  }

  function takeAnchor(): Anchor | null {
    if (!built || !el || layout.count === 0) return null;
    const top = -el.getBoundingClientRect().top;
    const first = layout.range(top, top + (window.innerHeight || 800))[0];
    const key = first ? layout.keyAt(first.index) : undefined;
    return first && key !== undefined ? { key, offset: top - first.rect.y } : null;
  }

  // Put the anchor item back at the same screen place after a reset changed the positions.
  function putAnchor(a: Anchor) {
    const i = layout.indexOf(a.key);
    const r = i >= 0 ? layout.rect(i) : undefined;
    if (!r || !el) return;
    window.scrollTo(0, Math.max(0, pageTop() + r.y + a.offset));
    computeWindow();
  }

  export function getAnchor(): { key: string; offset: number; sig: string } | null {
    const a = takeAnchor();
    return a ? { ...a, sig: getSig() } : null;
  }

  export function getSig(): string {
    return `${mode}|${zoom}|${width}`;
  }

  export function isReady(): boolean {
    return ready;
  }

  // With `offset` the tile top lands `offset` px below the screen top. Without it the tile is
  // left alone when it is on screen, else centered.
  export function scrollToKey(key: string, offset?: number): boolean {
    const i = built ? layout.indexOf(key) : -1;
    const r = i >= 0 ? layout.rect(i) : undefined;
    if (!r || !el) return false;
    const vh = window.innerHeight || 800;
    const top = -el.getBoundingClientRect().top;
    if (offset === undefined) {
      if (r.y >= top && r.y + r.h <= top + vh) return true;
      window.scrollTo(0, Math.max(0, pageTop() + r.y + r.h / 2 - vh / 2));
    } else {
      window.scrollTo(0, Math.max(0, pageTop() + r.y + offset));
    }
    computeWindow();
    return true;
  }

  // The rendered range changes only when its first or last index (or the layout) changes.
  function computeWindow() {
    if (!built || !el) return;
    const top = -el.getBoundingClientRect().top;
    const vh = window.innerHeight || 800;
    const buf = Math.max(1.5 * vh, 800);
    const list = layout.range(top - buf, top + vh + buf);
    const fi = focusKey !== undefined ? layout.indexOf(focusKey) : -1;
    const sig = `${ver}:${list.length}:${list[0]?.index}:${list[list.length - 1]?.index}:${fi}`;
    if (sig === winSig) return;
    winSig = sig;
    // Index order keeps the DOM in item order, so the pinned tile sits in its own place.
    // Local to one call, not rendered, so a plain Set is right.
    // eslint-disable-next-line svelte/prefer-svelte-reactivity
    const wanted = new Set(list.map((p) => p.index));
    if (fi >= 0) {
      for (let i = Math.max(0, fi - FOCUS_SPAN); i <= Math.min(layout.count - 1, fi + FOCUS_SPAN); i++) wanted.add(i);
    }
    const cells: Cell[] = [];
    for (const index of [...wanted].sort((a, b) => a - b)) {
      const item = items[index];
      const rect = layout.rect(index);
      if (item && rect) cells.push({ index, key: layout.keyAt(index) ?? keyOf(item), item, ...rect });
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
  let widthDirty = false;
  function schedule() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (widthDirty && el) {
        widthDirty = false;
        // Only a changed width resets; the phone address bar changes the height alone.
        if (el.clientWidth !== width) width = el.clientWidth;
      }
      flushFixups();
      computeWindow();
    });
  }

  $effect(() => {
    const node = el;
    if (!node) return;
    width = node.clientWidth;
    // A resize burst resets the layout once per frame; the reset keeps the anchor item in place.
    const ro =
      typeof ResizeObserver === "function"
        ? new ResizeObserver(() => {
            widthDirty = true;
            schedule();
          })
        : null;
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

  function onFocusIn(e: FocusEvent) {
    const cell = (e.target as Element | null)?.closest?.(".vcell");
    const pos = Number(cell?.getAttribute("aria-posinset"));
    const key = pos > 0 ? layout.keyAt(pos - 1) : undefined;
    if (key === undefined || key === focusKey) return;
    focusKey = key;
    computeWindow();
  }

  function onFocusOut(e: FocusEvent) {
    // Focus moving to another tile is followed by a focusin that sets the new key.
    const to = e.relatedTarget as Element | null;
    if (to?.closest?.(".vcell")) return;
    if (focusKey === undefined) return;
    focusKey = undefined;
    computeWindow();
  }

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
  {:else if built && placed.length > 0}
    <div class="vwin" role="list" style:height="{total}px" onfocusin={onFocusIn} onfocusout={onFocusOut}>
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
    <!-- Also the answer when the layout is built but its window holds no cell: rows never draw as nothing. -->
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
      revealed={revealedKeys.has(keyOf(item))}
      onreveal={() => revealedKeys.add(keyOf(item))}
      onopen={onopenweb ? () => onopenweb(item as WebItem) : undefined}
    />
  {:else}
    <Tile
      item={item as LibraryItem}
      variant={variant}
      aspect={aspect}
      onaspect={key !== undefined && aspect !== undefined ? (a) => reportAspect(key, a) : undefined}
      landscape={landscape}
      {selectable}
      href={itemHref(item as LibraryItem)}
      onnavigate={onnavigate}
      onopenitem={onopenitem}
      revealed={revealedKeys.has(keyOf(item))}
      onreveal={() => revealedKeys.add(keyOf(item))}
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
