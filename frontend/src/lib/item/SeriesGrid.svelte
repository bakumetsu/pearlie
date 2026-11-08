<script lang="ts">
  import type { LibraryItem } from "../api/client";
  import Icon from "../components/Icon.svelte";

  let { books, onopen }: {
    books: LibraryItem[];
    onopen: (book: LibraryItem) => void;
  } = $props();

  const continueBook = $derived<LibraryItem | null>(
    books.find(
      (b) =>
        typeof b.read_page !== "number" ||
        typeof b.page_count !== "number" ||
        b.read_page < b.page_count
    ) ?? null
  );
</script>

<button
  type="button"
  class="continue"
  aria-label="Continue reading"
  disabled={!continueBook}
  onclick={() => {
    if (continueBook) onopen(continueBook);
  }}
>
  <Icon name="play" size={20} />
  <span>Continue</span>
</button>

{#if books.length === 0}
  <p class="empty">No books</p>
{:else}
  <div class="grid">
    {#each books as book (book.id)}
      <button
        type="button"
        class="tile"
        aria-label={book.title}
        onclick={() => onopen(book)}
      >
        <div class="thumb">
          <img src={book.thumb_url} alt="" loading="lazy" />
        </div>
        <span class="tile-title">{book.title}</span>
        {#if typeof book.page_count === "number" && book.page_count > 0}
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
  .continue {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    background: var(--accent-bg);
    color: var(--accent);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    font-size: var(--t-14);
    padding: var(--s-2) var(--s-3);
  }
  .continue:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .empty {
    color: var(--muted);
    font-size: var(--t-14);
    margin: var(--s-3) 0 0;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: var(--s-3);
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: var(--s-2);
    text-align: left;
    color: var(--text);
  }
  .thumb {
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
