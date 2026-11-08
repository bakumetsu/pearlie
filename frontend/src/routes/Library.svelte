<script lang="ts">
  import { getApi, getRouter } from "../lib/ctx";
  import { linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import type { Kind, LibraryItem } from "../lib/api/client";
  import SectionRow from "../lib/components/SectionRow.svelte";
  import Tile from "../lib/components/Tile.svelte";
  import { onMount } from "svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();

  let h1: HTMLHeadingElement | undefined;

  onMount(() => {
    h1?.focus();
  });

  const ROWS: { kind: Kind; title: string; seeAll: string }[] = [
    { kind: "images", title: "Images", seeAll: "/library/stash/images" },
    { kind: "videos", title: "Videos", seeAll: "/library/stash/videos" },
    { kind: "series", title: "Series", seeAll: "/library/komga/series" },
    { kind: "books", title: "Books", seeAll: "/library/komga/books" },
  ];

  type RowState = {
    status: "loading" | "done" | "error";
    items: LibraryItem[];
    total: number | null;
    next_page: number | null;
  };

  let rowStates = $state<Record<Kind, RowState>>({
    images: { status: "loading", items: [], total: null, next_page: null },
    videos: { status: "loading", items: [], total: null, next_page: null },
    series: { status: "loading", items: [], total: null, next_page: null },
    books: { status: "loading", items: [], total: null, next_page: null },
  });

  const fav = $derived(match.query.get("favorite") === "true");

  async function loadRow(kind: Kind, signal?: AbortSignal) {
    rowStates[kind] = { status: "loading", items: [], total: null, next_page: null };
    try {
      const result = await api.list(
        kind,
        { page_size: 12, favorite: fav ? true : undefined },
        signal,
      );
      if (signal?.aborted) return;
      rowStates[kind] = {
        status: "done",
        items: result.items,
        total: result.total,
        next_page: result.next_page,
      };
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      rowStates[kind] = { status: "error", items: [], total: null, next_page: null };
    }
  }

  $effect(() => {
    const controller = new AbortController();
    for (const { kind } of ROWS) {
      loadRow(kind, controller.signal);
    }
    return () => controller.abort();
  });

  const allEmpty = $derived(
    ROWS.every(({ kind }) => rowStates[kind].status === "done" && rowStates[kind].items.length === 0),
  );

  function toggleFav(value: boolean) {
    const qs = new URLSearchParams(match.query);
    if (value) qs.set("favorite", "true");
    else qs.delete("favorite");
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
  }

  function seeAllHref(base: string): string {
    return fav ? `${base}?favorite=true` : base;
  }

  function onNav(e: MouseEvent) {
    linkClick(e, router);
  }
</script>

<div class="content">
  <h1 class="sr-only" tabindex="-1" bind:this={h1}>Library</h1>
  <h2 class="page-title">Library</h2>

  <div class="chips">
    <button
      class="chip"
      aria-pressed={!fav}
      onclick={() => toggleFav(false)}
    >
      All
    </button>
    <button
      class="chip"
      aria-pressed={fav}
      onclick={() => toggleFav(true)}
    >
      Favorites
    </button>
  </div>

  {#if allEmpty}
    <div class="empty-card">
      <p>Nothing here yet. Save something from Search</p>
      <a class="btn" href="/" onclick={onNav}>Go to Search</a>
    </div>
  {:else}
    {#each ROWS as row (row.kind)}
      {@const rs = rowStates[row.kind]}
      <SectionRow
        title={row.title}
        count={rs.total}
        seeAllHref={seeAllHref(row.seeAll)}
        onnavigate={onNav}
        error={rs.status === "error" ? `Could not load ${row.title}` : null}
        onretry={() => loadRow(row.kind)}
      >
        {#if rs.status === "loading"}
          {#each Array(6) as _}
            <div class="skeleton"></div>
          {/each}
        {:else}
          {#each rs.items as item (item.id)}
            <Tile item={item} href={`/item/${item.kind}/${item.id}`} onnavigate={onNav} />
          {/each}
        {/if}
      </SectionRow>
    {/each}
  {/if}
</div>

<style>
  .content {
    max-width: var(--content-max);
    margin: 0 auto;
    padding: var(--s-5);
    display: flex;
    flex-direction: column;
    gap: var(--s-4);
  }

  .page-title {
    font-size: var(--t-20);
    font-weight: 700;
    color: var(--text);
    margin: 0;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .chips {
    display: flex;
    gap: var(--s-2);
  }

  .chip {
    min-height: 44px;
    min-width: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 var(--s-3);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface);
    color: var(--text);
    font-size: var(--t-14);
    cursor: pointer;
  }

  .chip[aria-pressed="true"] {
    background: var(--accent-bg);
    border-color: var(--accent);
    color: var(--accent);
  }

  .skeleton {
    flex: 0 0 160px;
    height: 160px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
  }

  .empty-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--s-3);
    padding: var(--s-6) var(--s-4);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    color: var(--muted);
    font-size: var(--t-14);
  }

  .empty-card p {
    margin: 0;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    padding: 0 var(--s-4);
    background: var(--accent-bg);
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: var(--r-md);
    font-size: var(--t-14);
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
  }
</style>
