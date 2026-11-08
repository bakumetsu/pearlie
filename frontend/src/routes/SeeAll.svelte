<script lang="ts">
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import type { Kind, LibraryItem, WebItem } from "../lib/api/client";
  import { ApiError as ApiErrorClass } from "../lib/api/client";
  import { createGrid } from "../lib/stores/grid.svelte";
  import Tile from "../lib/components/Tile.svelte";
  import Icon from "../lib/components/Icon.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { onMount } from "svelte";
  import { SvelteURLSearchParams } from "svelte/reactivity";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();

  let h1: HTMLHeadingElement | undefined;
  let sentinel = $state<HTMLDivElement | undefined>();

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
      const loader = async (page: number, signal: AbortSignal) => {
        const r = await api.list(
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
        return { items: r.items, total: r.total ?? null, next_page: r.next_page ?? null };
      };
      grid.open(listKey, loader);
    } else {
      const loader = async (page: number, signal: AbortSignal) => {
        const r = await api.search({ q: qq, sources: [src], page }, signal);
        const s = r.sections?.find((x: { id: string }) => x.id === src);
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
    const qs = new SvelteURLSearchParams(match.query);
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
    const qs = new SvelteURLSearchParams(match.query);
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
      {#each Array.from({ length: 12 }, (_unused, n) => n) as n (n)}
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
/>
        {:else}
          {@const l = item as LibraryItem}
          <Tile
            item={l}
            href={`/item/${l.kind}/${l.id}`}
            onnavigate={onNav}
          />
        {/if}
      {/each}
    </div>
    <div class="sentinel" bind:this={sentinel}></div>
    {#if grid.hasMore}
      <button class="load-more" onclick={() => grid.loadMore()}>Load more</button>
    {/if}
  {/if}
</div>

<style>
  .content { max-width: var(--content-max); margin: 0 auto; padding: 0 var(--s-4); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
  .sticky-header { position: sticky; top: 0; background: var(--surface); z-index: 10; padding: var(--s-4) 0; }
  .header-row { display: flex; align-items: center; gap: var(--s-4); }
  .back-btn { min-width: 44px; min-height: 44px; display: grid; place-items: center; border: none; background: none; cursor: pointer; color: var(--text); }
  .header-title { font-size: 1.25rem; font-weight: 700; margin: 0; color: var(--text); }
  .controls { display: flex; gap: var(--s-4); margin-top: var(--s-4); }
  .sort-select { padding: var(--s-2) var(--s-4); border: 1px solid var(--text); border-radius: var(--s-2); background: var(--surface); color: var(--text); }
  .fav-toggle { min-height: 44px; display: flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-4); border: 1px solid var(--text); border-radius: var(--s-2); background: none; color: var(--text); cursor: pointer; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: var(--s-4); padding: var(--s-4) 0; }
  .skeleton { aspect-ratio: 3/4; background: var(--surface); border-radius: var(--s-2); }
  .error-box { padding: var(--s-4); text-align: center; color: var(--text); }
  .retry-btn { margin-top: var(--s-4); padding: var(--s-2) var(--s-4); border: none; border-radius: var(--s-2); background: var(--text); color: var(--surface); cursor: pointer; }
  .empty { text-align: center; padding: var(--s-8); color: var(--text); }
  .load-more { display: block; margin: var(--s-4) auto; padding: var(--s-2) var(--s-4); border: 1px solid var(--text); border-radius: var(--s-2); background: none; color: var(--text); cursor: pointer; }
  .sentinel { height: 1px; }
</style>
