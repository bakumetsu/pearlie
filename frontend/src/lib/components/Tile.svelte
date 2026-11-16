<script lang="ts">
  import Icon from "./Icon.svelte";
  import VideoCard from "./VideoCard.svelte";
  import type { LibraryItem, WebItem } from "../api/client";
  import { formatDuration } from "../format";
  import FavBadge from "./FavBadge.svelte";
  import { inView } from "../inView";
  import { takeSlot } from "../gifSlots";
  import { options } from "../stores/options.svelte";

  let { item, href, onnavigate, saveState = "idle", savedHref, onsave, onopen, onopenitem, variant = "grid", aspect, onaspect, landscape = false, revealed: revealedProp = false, onreveal }: {
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
    // Reports the real picture shape when it differs from `aspect` by more than 3 %.
    onaspect?: (aspect: number) => void;
    landscape?: boolean;
    // A grid that unmounts tiles keeps the reveal for them: it passes the state and hears the change.
    revealed?: boolean;
    onreveal?: () => void;
  } = $props();

  const isWeb = $derived("post_id" in item);
  // Direct web thumbs fall back thumb_url -> preview_url -> placeholder with Retry;
  // proxied ones (/api/media/web/) go straight to the placeholder with Retry.
  let stage = $state<0 | 1 | 2>(0);
  let lastThumb = "";
  $effect(() => {
    const t = isWeb ? (item as WebItem).thumb_url : "";
    if (t !== lastThumb) {
      lastThumb = t;
      stage = 0;
    }
  });
  function webSrc(w: WebItem): string {
    return stage === 1 ? w.preview_url : w.thumb_url || w.preview_url;
  }
  function onWebError() {
    // The GIF failed after the preload: back to the still, keep the stage.
    if (gifReady) {
      gifReady = false;
      return;
    }
    const w = item as WebItem;
    // A proxied thumb never falls back to preview_url (the full file): placeholder + Retry.
    const proxied = w.thumb_url.startsWith("/api/media/web/");
    if (!proxied && stage === 0 && w.preview_url && w.preview_url !== w.thumb_url) stage = 1;
    else stage = 2;
  }
  let revealedLocal = $state(false);
  const blurred = $derived(!revealedLocal && !revealedProp && item.blur != null);
  function reveal() {
    revealedLocal = true;
    onreveal?.();
  }

  // Animated GIF in the grid: the backend sets gif_url only for a small GIF. The still stays
  // until the GIF has loaded; off screen, blurred, reduced motion or the setting off: still.
  let visible = $state(false);
  let reduced = $state(false);
  let gifReady = $state(false);
  const gifUrl = $derived(item.gif_url ?? null);
  const wantGif = $derived(
    visible && !!gifUrl && (options.values?.gif_grid ?? true) && !reduced && !blurred && stage !== 2,
  );
  $effect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    reduced = mq.matches;
    const on = () => (reduced = mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  });
  $effect(() => {
    if (!wantGif || !gifUrl) return;
    const pre = new Image();
    let release: (() => void) | null = null;
    pre.onload = () => {
      release = takeSlot(() => (gifReady = false));
      gifReady = true;
    };
    pre.src = gifUrl;
    return () => {
      pre.onload = null;
      pre.onerror = null;
      pre.src = "";
      release?.();
      gifReady = false;
    };
  });
  const track = (visibleNow: boolean) => (visible = visibleNow);

  function onImgLoad(e: Event) {
    const img = e.currentTarget as HTMLImageElement;
    if (!onaspect || aspect == null || !(aspect > 0) || !img.naturalWidth || !img.naturalHeight) return;
    const real = img.naturalWidth / img.naturalHeight;
    if (Math.abs(real - aspect) / aspect > 0.03) onaspect(real);
  }

  function handleMediaClick(e: MouseEvent) {
    if (blurred) {
      e.preventDefault();
      e.stopPropagation();
      reveal();
    }
  }

  function handleMediaKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      if (blurred) {
        reveal();
      }
    }
  }

  function handleOpenClick(e: MouseEvent) {
    if (blurred) {
      e.preventDefault();
      reveal();
      return;
    }
    // A plain click keeps the in-page open; middle or Ctrl+click follows the link into a new tab.
    const plain = e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey;
    if (href && !plain) return;
    e.preventDefault();
    onopen?.();
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
    if (isWeb) {
      const w = item as WebItem;
      if (w.source === "nhentai") return "2 / 3";
      // Booru posts keep their native shape, like the library image card.
      if (w.width > 0 && w.height > 0) return `${w.width} / ${w.height}`;
      return "1 / 1";
    }
    return "2 / 3";
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
  <div class="tile web {variant}" class:cv={variant !== "list"} style:aspect-ratio={variant !== "list" ? aspectRatio : undefined}>
    <div class="media" style:aspect-ratio={aspectRatio} use:inView={track}>
      {#if !w.thumb_url && !w.preview_url}
        <div class="thumb-fail">
          <Icon name="image" size={24} />
          <span class="no-preview">No preview</span>
        </div>
      {:else if stage === 2}
        <div class="thumb-fail">
          <Icon name="image" size={24} />
          <button class="retry" onclick={(e) => { e.stopPropagation(); stage = 0; }}>Retry</button>
        </div>
      {:else}
        <img src={gifReady && gifUrl ? gifUrl : webSrc(w)} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" class:blur-img={blurred} onerror={onWebError} onload={onImgLoad} />
      {/if}
      {#if href}
        <a class="open" {href} onclick={handleOpenClick} aria-label={`${w.source} #${w.post_id}`} title={`${w.source} #${w.post_id}`}></a>
      {:else}
        <button class="open" onclick={handleOpenClick} aria-label={`${w.source} #${w.post_id}`} title={`${w.source} #${w.post_id}`}></button>
      {/if}
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
      {#if saveState === "idle" && !w.saved && w.saveable !== false}
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
    {/if}
  </div>
{:else}
  {@const l = item as LibraryItem}
  <a class="tile lib {variant}" class:cv={variant !== "list" && l.kind === "image"} style:aspect-ratio={variant !== "list" && l.kind === "image" ? aspectRatio : undefined} href={href} data-key={`${l.kind}:${l.id}`} onclick={handleLibClick}>
    {#if l.kind === "video"}
      <VideoCard item={l} {variant} {aspectRatio} {blurred} {landscape} meta={metaLine()} onmediaclick={handleMediaClick} onmediakeydown={handleMediaKeydown} />
    {:else}
    <div class="media" style:aspect-ratio={aspectRatio} onclick={handleMediaClick} role="button" tabindex="0" onkeydown={handleMediaKeydown} use:inView={track}>
      <img src={gifReady && gifUrl ? gifUrl : l.thumb_url} alt="" loading="lazy" decoding="async" class:blur-img={blurred} onload={onImgLoad} />
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
  /* Off-screen tiles skip layout and paint; aspect-ratio keeps their height stable. */
  .tile.cv {
    content-visibility: auto;
    contain-intrinsic-size: auto 200px;
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
  .thumb-fail {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--s-1);
    color: var(--muted);
  }
  .retry {
    position: relative;
    z-index: 1;
    min-height: 44px;
    padding: 0 var(--s-3);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    color: var(--text);
    font-size: var(--t-13);
    cursor: pointer;
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
  .save-btn {
    opacity: 0;
  }
  .tile:hover .save-btn,
  .tile:focus-within .save-btn,
  .save-btn:focus-visible {
    opacity: 1;
  }
  @media (hover: none) {
    .save-btn {
      opacity: 1;
    }
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
  @keyframes tick-in {
    from {
      transform: scale(0.6);
      opacity: 0;
    }
  }
  .badge {
    animation: tick-in 0.2s ease-out;
  }
  @media (prefers-reduced-motion: reduce) {
    .spin,
    .badge {
      animation: none;
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
