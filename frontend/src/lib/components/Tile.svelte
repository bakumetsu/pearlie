<script lang="ts">
  import Icon from "./Icon.svelte";
  import VideoCard from "./VideoCard.svelte";
  import type { LibraryItem, WebItem } from "../api/client";
  import { formatDuration } from "../format";
  import FavBadge from "./FavBadge.svelte";

  let { item, href, onnavigate, saveState = "idle", savedHref, onsave, onopen, onopenitem, variant = "grid", aspect, landscape = false }: {
    item: LibraryItem | WebItem;
    href?: string;
    onnavigate?: (e: MouseEvent) => void;
    saveState?: "idle" | "queued" | "in_library";
    savedHref?: string;
    onsave?: () => void;
    onopen?: () => void;
    onopenitem?: (item: LibraryItem) => void;
    variant?: "grid" | "wall" | "masonry" | "list";
    aspect?: number;
    landscape?: boolean;
  } = $props();

  const isWeb = $derived("post_id" in item);
  let revealed = $state(false);
  const blurred = $derived(!revealed && item.blur != null);

  function handleMediaClick(e: MouseEvent) {
    if (blurred) {
      e.preventDefault();
      e.stopPropagation();
      revealed = true;
    }
  }

  function handleMediaKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      if (blurred) {
        revealed = true;
      }
    }
  }

  function handleOpenClick() {
    if (blurred) {
      revealed = true;
    } else {
      onopen?.();
    }
  }

  function handleLibClick(e: MouseEvent) {
    const l = item as LibraryItem;
    const plain = e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey;
    if (onopenitem && l.kind === "image" && plain && !e.defaultPrevented) {
      e.preventDefault();
      onopenitem(l);
      return;
    }
    onnavigate?.(e);
  }



  function getProgress(): number {
    if (isWeb) return 0;
    const lib = item as LibraryItem;
    if (lib.kind === "book" && lib.page_count && lib.read_page != null)
      return (lib.read_page / lib.page_count) * 100;
    if (lib.kind === "series" && lib.book_count && lib.read_count != null)
      return (lib.read_count / lib.book_count) * 100;
    return 0;
  }
  const progressPct = $derived(getProgress());

  const aspectRatio = $derived.by(() => {
    if (variant === "list") return "1 / 1";
    if (landscape && !isWeb && (item as LibraryItem).kind === "video") return "16 / 9";
    if (variant === "wall" || variant === "masonry") {
      if (aspect != null && Number.isFinite(aspect) && aspect > 0) return `${aspect}`;
    }
    return isWeb ? "1 / 1" : "2 / 3";
  });

  function metaLine(): string {
    const l = item as LibraryItem;
    const parts: string[] = [];
    if (l.width != null && l.height != null) parts.push(`${l.width}x${l.height}`);
    if (l.kind === "video" && l.duration_s != null) parts.push(formatDuration(l.duration_s));
    if (l.kind === "book" && l.page_count != null) parts.push(`${l.page_count} pages`);
    if (l.kind === "series" && l.book_count != null) parts.push(`${l.book_count} books`);
    if (l.rating != null) parts.push(`Rating ${l.rating}`);
    return parts.join(" - ");
  }
</script>

{#if isWeb}
  {@const w = item as WebItem}
  <div class="tile web {variant}">
    <div class="media" style:aspect-ratio={aspectRatio}>
      <img src={w.thumb_url} alt="" loading="lazy" class:blur-img={blurred} />
      <button class="open" onclick={handleOpenClick} aria-label="Open preview"></button>
      {#if blurred}
        <div class="warn-overlay">Warn: {w.blur!.tag}</div>
      {/if}
      {#if saveState === "in_library" || w.saved}
        {#if savedHref}
          <a class="badge" href={savedHref} onclick={onnavigate}><Icon name="check" size={12} />In library</a>
        {:else}
          <span class="badge"><Icon name="check" size={12} />In library</span>
        {/if}
      {/if}
      {#if saveState === "idle" && !w.saved}
        <button class="save-btn" onclick={onsave} aria-label="Save"><Icon name="download" size={18} /></button>
      {:else if saveState === "queued"}
        <button class="save-btn" disabled aria-label="Queued"><span class="spin"><Icon name="loader" size={18} /></span></button>
      {/if}
    </div>
    {#if variant === "list"}
      <div class="info">
        <div class="title">{w.title ?? `${w.source} #${w.post_id}`}</div>
        {#if w.title}<div class="meta">{w.source} #{w.post_id}</div>{/if}
      </div>
    {:else}
      <div class="title">{w.title ?? `${w.source} #${w.post_id}`}</div>
    {/if}
  </div>
{:else}
  {@const l = item as LibraryItem}
  <a class="tile lib {variant}" href={href} data-key={`${l.kind}:${l.id}`} onclick={handleLibClick}>
    {#if l.kind === "video"}
      <VideoCard item={l} {variant} {aspectRatio} {blurred} {landscape} meta={metaLine()} onmediaclick={handleMediaClick} onmediakeydown={handleMediaKeydown} />
    {:else}
    <div class="media" style:aspect-ratio={aspectRatio} onclick={handleMediaClick} role="button" tabindex="0" onkeydown={handleMediaKeydown}>
      <img src={l.thumb_url} alt="" loading="lazy" class:blur-img={blurred} />
      {#if variant !== "list" && l.favorite}
        <FavBadge />
      {/if}

      {#if l.kind === "series" || l.kind === "book"}
        <div class="progress" style:width="{progressPct}%"></div>
      {/if}
      {#if blurred}
        <div class="warn-overlay">Warn: {l.blur!.tag}</div>
      {/if}
    </div>
    {#if variant === "list"}
      <div class="info">
        <div class="title">{l.title}</div>
        {#if metaLine()}
          <div class="meta">{metaLine()}</div>
        {/if}
      </div>
    {:else if l.kind !== "image"}
      <div class="title">{l.title}</div>
    {/if}
    {/if}
  </a>
{/if}

<style>
  .tile {
    display: block;
    cursor: pointer;
    text-decoration: none;
    color: inherit;
  }
  .tile.lib {
    display: block;
    min-width: 0;
  }
  .media {
    position: relative;
    overflow: hidden;
    border-radius: var(--r-md);
    background: var(--surface);
  }
  .media img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
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
  .duration {
    position: absolute;
    bottom: var(--s-1);
    right: var(--s-1);
    z-index: 1;
    background: rgba(0, 0, 0, 0.7);
    color: var(--text);
    font-size: var(--t-12);
    padding: 2px var(--s-1);
    border-radius: var(--r-sm);
  }
  .progress {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 4px;
    background: var(--progress);
    z-index: 1;
  }
  .title {
    font-size: var(--t-13);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: var(--s-1);
    color: var(--text);
  }
  /* Web tile */
  .web .media {
    aspect-ratio: 1 / 1;
  }
  .open {
    position: absolute;
    inset: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    width: 100%;
    height: 100%;
    z-index: 0;
  }
  .badge {
    position: absolute;
    top: var(--s-1);
    left: var(--s-1);
    z-index: 2;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--ok-bg);
    color: var(--ok-fg);
    font-size: var(--t-12);
    padding: 2px var(--s-1);
    border-radius: var(--r-sm);
    text-decoration: none;
  }
  .save-btn {
    position: absolute;
    bottom: var(--s-1);
    right: var(--s-1);
    z-index: 2;
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.55);
    border: none;
    border-radius: var(--r-md);
    color: var(--text);
    cursor: pointer;
  }
  .save-btn:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }
  .spin {
    display: inline-flex;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  /* List variant */
  .tile.list {
    display: flex;
    align-items: center;
    gap: var(--s-4);
    min-height: 56px;
    padding: var(--s-2) 0;
  }
  .tile.list .media {
    width: var(--list-thumb, 64px);
    flex: none;
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
