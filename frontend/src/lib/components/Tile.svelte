<script lang="ts">
  import Icon from "./Icon.svelte";
  import type { LibraryItem, WebItem } from "../api/client";

  let { item, href, onnavigate, saveState = "idle", savedHref, onsave, onopen }: {
    item: LibraryItem | WebItem;
    href?: string;
    onnavigate?: (e: MouseEvent) => void;
    saveState?: "idle" | "queued" | "in_library";
    savedHref?: string;
    onsave?: () => void;
    onopen?: () => void;
  } = $props();

  const isWeb = "post_id" in item;
  let revealed = $state(false);
  const blurred = $derived(!revealed && item.blur != null);

  function handleMediaClick(e: MouseEvent) {
    if (blurred) {
      e.preventDefault();
      e.stopPropagation();
      revealed = true;
    }
  }

  function handleOpenClick() {
    if (blurred) {
      revealed = true;
    } else {
      onopen?.();
    }
  }

  function formatDuration(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    return `${m}:${String(sec).padStart(2, "0")}`;
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

  const aspectRatio = $derived(
    isWeb
      ? "1 / 1"
      : (item as LibraryItem).kind === "video"
        ? "16 / 9"
        : (item as LibraryItem).kind === "image"
          ? "1 / 1"
          : "2 / 3"
  );
</script>

{#if isWeb}
  {@const w = item as WebItem}
  <div class="tile web">
    <div class="media">
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
    <div class="title">{w.title ?? `${w.source} #${w.post_id}`}</div>
  </div>
{:else}
  {@const l = item as LibraryItem}
  <a class="tile lib" href={href} onclick={onnavigate}>
    <div class="media" style:aspect-ratio={aspectRatio} onclick={handleMediaClick}>
      <img src={l.thumb_url} alt="" loading="lazy" class:blur-img={blurred} />
      {#if l.favorite}
        <span class="fav"><Icon name="heart-filled" size={14} /></span>
      {/if}
      {#if l.kind === "video" && l.duration_s != null}
        <span class="duration">{formatDuration(l.duration_s)}</span>
      {/if}
      {#if l.kind === "series" || l.kind === "book"}
        <div class="progress" style:width="{progressPct}%"></div>
      {/if}
      {#if blurred}
        <div class="warn-overlay">Warn: {l.blur!.tag}</div>
      {/if}
    </div>
    {#if l.kind !== "image"}
      <div class="title">{l.title}</div>
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
  }
  .media {
    position: relative;
    overflow: hidden;
    border-radius: var(--r-md);
    background: var(--surface);
  }
  .media img {
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
  .fav {
    position: absolute;
    top: var(--s-1);
    right: var(--s-1);
    z-index: 1;
    color: var(--danger-fg);
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
</style>
