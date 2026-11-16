<script lang="ts">
  import { onMount } from "svelte";
  import type { LibraryItem } from "../api/client";
  import Icon from "../components/Icon.svelte";
  import { isFinished, pickContinue } from "./seriesProgress";

  let { books, onopen }: {
    books: LibraryItem[];
    onopen: (book: LibraryItem) => void;
  } = $props();

  const continueBook = $derived(pickContinue(books));
  let gridEl = $state<HTMLElement | null>(null);

  // Long series: bring the Continue book into view once after load.
  onMount(() => {
    gridEl?.querySelector<HTMLElement>("[data-cont]")?.scrollIntoView?.({ block: "nearest" });
  });
</script>

{#if books.length === 0}
  <p class="empty">No books</p>
{:else}
  <div class="grid" bind:this={gridEl}>
    {#each books as book (book.id)}
      {@const done = isFinished(book)}
      {@const cont = continueBook?.id === book.id}
      <button
        type="button"
        class="tile"
        class:cont
        aria-label={done ? book.title + ", read" : book.title}
        onclick={() => onopen(book)}
        data-cont={cont ? "1" : undefined}
      >
        <div class="thumb">
          <img src={book.thumb_url} alt="" loading="lazy" />
          {#if done}<span class="tick" aria-hidden="true"><Icon name="check" size={14} /></span>{/if}
        </div>
        <span class="tile-title">{book.title}</span>
        {#if typeof book.page_count === "number" && book.page_count > 0 && (book.read_page ?? 0) > 0}
          <div class="progress">
            <div
              class="bar"
              style="width: {Math.min(100, ((book.read_page ?? 0) / book.page_count) * 100)}%"
            ></div>
          </div>
        {/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  .empty {
    color: var(--muted);
    font-size: var(--t-14);
    margin: var(--s-3) 0 0;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: var(--s-3);
    margin-top: var(--s-4);
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    min-height: 44px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: var(--s-2);
    text-align: left;
    color: var(--text);
    font: inherit;
    cursor: pointer;
  }
  .tile.cont { border: 2px solid var(--progress); padding: calc(var(--s-2) - 1px); }
  .tile:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .thumb {
    position: relative;
    aspect-ratio: 2 / 3;
    overflow: hidden;
    border-radius: var(--r-sm);
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .tick {
    position: absolute;
    right: 4px;
    top: 4px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: rgb(0 0 0 / .65);
    color: #fff;
    display: grid;
    place-items: center;
  }
  .tile-title {
    font-size: var(--t-12);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .progress {
    height: 4px;
    background: var(--line);
    border-radius: var(--r-sm);
    overflow: hidden;
  }
  .bar {
    height: 100%;
    background: var(--progress);
    border-radius: var(--r-sm);
  }
</style>
