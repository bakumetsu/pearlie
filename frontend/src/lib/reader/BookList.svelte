<script lang="ts">
  import type { LibraryItem } from "../api/client";

  let {
    books,
    currentId,
    notice,
    onpick,
    onclose,
  } = $props<{
    books: LibraryItem[];
    currentId: string;
    notice: string | null;
    onpick: (book: LibraryItem) => void;
    onclose: () => void;
  }>();
</script>

<div
  role="dialog"
  aria-label="Books"
  class="bk"
  onkeydown={(e: KeyboardEvent) => {
    if (e.key === "Escape") onclose();
  }}
>
  {#if notice}
    <p class="notice">{notice}</p>
  {/if}

  <ul class="list" role="list">
    {#each books as b (b.id)}
      <li>
        <button
          type="button"
          class="row"
          class:on={b.id === currentId}
          aria-current={b.id === currentId}
          onclick={() => onpick(b)}
        >
          {#if b.thumb_url}
            <img src={b.thumb_url} alt="" loading="lazy" width={36} height={54} />
          {:else}
            <span class="ph" aria-hidden="true"></span>
          {/if}
          <span class="meta">
            <span class="title">{b.title}</span>
            <span class="prog">{b.read_page ?? 0} / {b.page_count ?? "–"}</span>
          </span>
        </button>
      </li>
    {:else}
      <li class="empty">No books</li>
    {/each}
  </ul>
</div>

<style>
  .bk {
    position: absolute;
    top: 72px;
    right: 16px;
    width: 320px;
    max-height: 60vh;
    overflow: auto;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-radius: var(--r-lg, 12px);
    padding: var(--s-2, 8px);
    font-size: var(--t-13);
    z-index: 40;
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.5);
  }

  .bk :focus-visible {
    outline: 2px solid var(--accent);
  }

  .notice {
    margin: 0;
    padding: var(--s-2, 8px);
    font-size: 12px;
    color: var(--muted);
  }

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .empty {
    padding: var(--s-3, 12px);
    color: var(--muted);
    font-size: 12px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--s-3, 12px);
    width: 100%;
    min-width: 44px;
    min-height: 44px;
    padding: 6px var(--s-2, 8px);
    background: none;
    border: 1px solid transparent;
    border-radius: var(--r-md, 10px);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .row:hover {
    background: var(--line, #26262b);
  }

  .row.on {
    background: var(--accent-bg);
    border-color: var(--accent);
  }

  .row img,
  .ph {
    width: 36px;
    height: 54px;
    flex: none;
  }

  .row img {
    object-fit: cover;
    border-radius: 4px;
  }

  .ph {
    border-radius: 4px;
    background: var(--line, #26262b);
  }

  .meta {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    line-height: 1.25;
  }

  .title {
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .prog {
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
</style>
