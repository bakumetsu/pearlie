<script lang="ts">
  import { getApi, getRouter } from "../lib/ctx";
  import { linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import type { Kind, LibraryItem, WebItem, ApiError } from "../lib/api/client";
  import { ApiError as ApiErrorClass } from "../lib/api/client";
  import { createGrid } from "../lib/stores/grid.svelte";
  import Tile from "../lib/components/Tile.svelte";
  import Icon from "../lib/components/Icon.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { onMount } from "svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();

  let h1: HTMLHeadingElement | undefined;
  let sentinel: HTMLDivElement | undefined;

  onMount(() => {
    h1?.focus();
  });

  const source = $derived.by(() => {
    switch (match.name) {
      case "library_images": return "stash_images";
      case "library_videos": return "stash_videos";
      case "library_series": return "komga_series";
      case "library_books": return "komga_books";
      default: return match.query.get("source") ?? "";
    }
  });

  const q = $derived(match.query.get("q") ?? "");
  const sort = $derived(match.query.get("sort") ?? "");
  const favorite = $derived(match.query.get("favorite") === "true");
  const seed = $derived(match.query.get("seed") ?? undefined);

  function sourceToKind(s: string): Kind | null {
    if (s === "stash_images") return "images";
    if (s === "stash_videos") return "videos";
    if (s === "komga_series") return "series";
    if (s === "komga_books") return "books";
    return null;
  }

  const kind = $derived(sourceToKind(source));
  const isLibrary = $derived(kind !== null);

  const title = $derived.by(() => {
    switch (source) {
      case "stash_images": return "Images";
      case "stash_videos": return "Videos";
      case "komga_series": return "Series";
      case "komga_books": return "Books";
      default: return source || "Results";
    }
  });

  function keyOf(t: LibraryItem | WebItem): string {
    return "post_id" in t ? t.source + ":" + t.post_id : t.kind + ":" + t.id;
  }

  const grid = createGrid<LibraryItem | WebItem>(keyOf);

  const listKey = $derived(
    [source, q, sort, favorite ? "1" : "0", seed ?? ""].join("|"),
  );

  $effect(() => {
    const k = sourceToKind(source);
    const src = source;
    const qq = q;
    const srt = sort;
    const fav = favorite;

    if (k) {
      const loader = (page: number, signal: AbortSignal) =>
        api.list(
          k,
          {
            page,
            page_size: 60,
            q: qq || undefined,
            sort: (srt || undefined) as "newest" | "rating" | "random" | undefined,
            favorite: fav ? true : undefined,
          },
          signal,
        );
      grid.open(listKey, loader);
    } else {
      const loader = async (page: number, signal: AbortSignal) => {
        const r = await api.search({ q: qq, sources: [src], page }, signal);
        const s = r.sections?.find((x) => x.id === src);
        return {
          items: s?.items ?? [],
          total: s?.total ?? null,
          next_page: s?.next_page ?? null,
        };
      };
      grid.open(listKey, loader);
    }
  });

  // --- save state for web items ---
  let saveStates = $state<Record<string, "queued" | "in_library">>({});

  async function handleSave(item: WebItem) {
    const key = item.source + ":" + item.post_id;
    saveStates[key] = "queued";
    try {
      await api.save({ source: item.source, post_id: item.post_id });
      toasts.push({ kind: "info", message: "Added to queue", actionLabel: "View", href: "/queue" });
    } catch (e) {
      if (e instanceof ApiErrorClass && e.status === 409) {
        saveStates[key] = "in_library";
      } else {
        delete saveStates[key];
        toasts.push({ kind: "error", message: "Could not save. Try again." });
      }
    }
  }

  // --- URL query updates ---
  function onSortChange(value: string) {
    const qs = new URLSearchParams(match.query);
    if (value) {
      qs.set("sort", value);
      if (value === "random") {
        qs.set("seed", Math.random().toString(36).slice(2, 8));
      } else {
        qs.delete("seed");
      }
    } else {
      qs.delete("sort");
      qs.delete("seed");
    }
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
  }

  function onFavToggle() {
    const qs = new URLSearchParams(match.query);
    if (favorite) qs.delete("favorite");
    else qs.set("favorite", "true");
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
  }

  function onNav(e: MouseEvent) {
    linkClick(e, router);
  }

  // --- IntersectionObserver for infinite scroll ---
  onMount(() => {
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          grid.loadMore();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  });
</script>

<div class="content">
  <h1 class="sr-only" tabindex="-1" bind:this={h1}>{title}</h1>

  <header class="sticky-header">
    <div class="header-row">
      <button class="back-btn" aria-label="Back" onclick={() => history.back()}>
        <Icon name="arrow-left" size={20} />
      </button>
      <h2 class="header-title">{title} ({grid.total ?? "…"})</h2>
    </div>

    {#if q}
      <div class="q-chips">
        <span class="q-chip">{q}</span>
      </div>
    {/if}

    {#if isLibrary}
      <div class="controls">
        <select aria-label="Sort" class="sort-select" value={sort} onchange={(e) => onSortChange((e.target as HTMLSelectElement).value)}>
          <option value="">Newest</option>
          <option value="rating">Rating</option>
          <option value="random">Random</option>
        </select>
        <button
          class="fav-toggle"
          aria-pressed={favorite}
          onclick={onFavToggle}
        >
          <Icon name={favorite ? "heart-filled" : "heart"} size={16} />
          Favorites
        </button>
      </div>
    {/if}
  </header>

  {#if grid.status === "loading" || grid.status === "idle"}
    <div class="grid">
      {#each Array(12) as _}
        <div class="skeleton"></div>
      {/each}
    </div>
  {:else if grid.status === "error"}
    <div class="error-box">
      <p>Could not load this list.</p>
      <button class="retry-btn" onclick={() => grid.retry()}>Retry</button>
    </div>
  {:else if grid.items.length === 0}
    <div class="empty">Nothing here.</div>
  {:else}
    <div class="grid">
      {#each grid.items as item (keyOf(item))}
        {#if "post_id" in item}
          {@const w = item as WebItem}
          {@const saveKey = w.source + ":" + w.post_id}
          <Tile
            item={w}
            saveState={saveStates[saveKey] ?? "idle"}
            onsave={() => handleSave(w)}
