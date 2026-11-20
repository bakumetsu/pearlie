<script lang="ts">
  import { onMount } from "svelte";
  import type { LibraryItem } from "../api/client";
  import Icon from "../components/Icon.svelte";
  import { isFinished } from "./seriesProgress";

  // continueId marks the Continue book (outline and scroll); null when the primary button says Read.
  let { books, continueId = null, view = "grid", onopen }: {
    books: LibraryItem[];
    view?: "grid" | "list";
    continueId?: string | null;
    onopen: (book: LibraryItem) => void;
  } = $props();
  const pct = (b: LibraryItem): number =>
    typeof b.page_count === "number" && b.page_count > 0 && (b.read_page ?? 0) > 0
      ? Math.min(100, ((b.read_page ?? 0) / b.page_count) * 100)
      : 0;
  let gridEl = $state<HTMLElement | null>(null);

  // Long series: bring the Continue book into view once after load.
  onMount(() => {
    gridEl?.querySelector<HTMLElement>("[data-cont]")?.scrollIntoView?.({ block: "nearest" });
  });
</script>

{#if books.length === 0}
  <p class="empty">No books</p>
{:else}
  <div class={view === "grid" ? "grid" : "lv"} bind:this={gridEl}>
    {#each books as book, i (book.id)}
      {@const done = isFinished(book)}
      {@const cont = continueId !== null && continueId === book.id}
      {@const p = pct(book)}
      <button
        type="button"
        class={view === "grid" ? "tile" : "row"}
        class:cont
        aria-label={done ? book.title + ", read" : book.title}
        onclick={() => onopen(book)}
        data-cont={cont ? "1" : undefined}
      >
        {#if view === "grid"}
          <div class="th">
            <img src={book.thumb_url} alt="" loading="lazy" />
            <span class="num">{i + 1}</span>
            {#if done}<span class="tick" aria-hidden="true"><Icon name="check" size={14} /></span>{/if}
            {#if p > 0 && !done}<div class="pb"><i style="width: {p}%"></i></div>{/if}
          </div>
          <span class="tn">{book.title}</span>
        {:else}
          <span class="rn">{i + 1}</span>
          <img class="rt" src={book.thumb_url} alt="" loading="lazy" />
          <span class="tn">{book.title}</span>
          {#if done}<span class="tick" aria-hidden="true"><Icon name="check" size={14} /></span>{/if}
        {/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  .empty { color: var(--muted); font-size: var(--t-14); margin: var(--s-3) 0 0; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-3); margin-top: var(--s-4); }
  .lv { display: flex; flex-direction: column; gap: var(--s-1); margin-top: var(--s-4); }
  @media (min-width: 900px) { .grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); } }
  .tile { display: flex; flex-direction: column; gap: 8px; padding: 0; min-width: 0; min-height: 44px; background: transparent; border: 0; border-radius: 12px; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .tile:focus-visible, .row:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .th { position: relative; aspect-ratio: 2 / 3; overflow: hidden; border-radius: 12px; background: var(--surface); }
  .tile:hover .th { box-shadow: 0 0 0 2px var(--line-strong); }
  .tile.cont .th { box-shadow: 0 0 0 2px var(--progress); }
  .th img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .num { position: absolute; left: 6px; top: 6px; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 999px; background: rgb(0 0 0 / .65); color: #fff; font-size: var(--t-12); display: grid; place-items: center; }
  @media (hover: hover) {
    .num { opacity: 0; transition: opacity .15s; }
    .tile:hover .num, .tile:focus-visible .num { opacity: 1; }
  }
  .tick { position: absolute; right: 6px; top: 6px; width: 22px; height: 22px; border-radius: 50%; background: rgb(0 0 0 / .65); color: #fff; display: grid; place-items: center; }
  .pb { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgb(0 0 0 / .5); }
  .pb i { display: block; height: 100%; background: var(--progress); }
  .tn { font-size: var(--t-12); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-width: 0; }
  .row { position: relative; display: flex; align-items: center; gap: var(--s-3); min-height: 56px; padding: 4px; background: transparent; border: 0; border-radius: 8px; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .row:hover { background: var(--surface); }
  .row.cont { box-shadow: inset 0 0 0 2px var(--progress); }
  .rn { width: 28px; text-align: right; color: var(--muted); font-size: var(--t-13); flex: none; }
  .rt { width: 36px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 4px; background: var(--surface); flex: none; }
  .row .tn { flex: 1; font-size: var(--t-14); }
  .row .tick { position: static; flex: none; }
</style>
