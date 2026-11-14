<script lang="ts">
  import type { Api, LibraryItemDetail } from "../api/client";
  import { pageSrc, isCompleted } from "../reader/pages";
  import { gatedSrc } from "../webImageQueue";
  import Icon from "../components/Icon.svelte";

  // ondelete: hook for the trash flow of D-14/T-75. Delete is not built here, so nothing passes it yet.
  let { detail, api, onread, onerror, ondelete }: {
    detail: LibraryItemDetail;
    api: Pick<Api, "saveProgress">;
    onread: (page?: number) => void;
    onerror: (message: string) => void;
    ondelete?: () => void;
  } = $props();

  let readPage = $state<number | null>(null);
  $effect(() => {
    readPage = detail.read_page ?? null;
  });

  const count = $derived(detail.page_count ?? 0);
  const pages = $derived(Array.from({ length: count }, (_, i) => i + 1));
  const done = $derived(isCompleted(readPage ?? 0, count));
  const last = $derived(readPage && readPage > 1 && !done ? readPage : null);
  const thumbTpl = $derived(detail.page_thumb_url ?? "");

  let busy = $state(false);
  async function markRead() {
    if (busy || count < 1) return;
    busy = true;
    try {
      await api.saveProgress(detail.id, count);
      readPage = count;
    } catch {
      onerror("Could not mark this book as read");
    } finally {
      busy = false;
    }
  }
</script>

<div class="book">
  <section class="hero">
    <img class="cover" src={detail.thumb_url} alt={detail.title} />
    <div class="info">
      <h2 class="title">{detail.title}</h2>
      <div class="actions">
        {#if count > 0}
          <button class="btn primary" type="button" onclick={() => onread()}>
            <Icon name="book" size={20} />{last ? "Continue" : "Read"}
          </button>
          <button
            class="ib"
            type="button"
            aria-label={done ? "Read" : "Mark read"}
            title={done ? "Read" : "Mark read"}
            disabled={done || busy}
            onclick={markRead}
          >
            <Icon name="check" size={20} />
          </button>
        {/if}
        {#if ondelete}
          <button class="ib" type="button" aria-label="Delete" title="Delete" onclick={ondelete}>
            <Icon name="trash" size={20} />
          </button>
        {/if}
      </div>
    </div>
  </section>

  {#if count > 0 && thumbTpl}
    <ul class="grid">
      {#each pages as n (n)}
        <li>
          <button class="thumb" class:last={last === n} type="button" aria-label={"Page " + n} onclick={() => onread(n)}>
            <img alt="" use:gatedSrc={{ src: pageSrc(thumbTpl, n), prio: n <= 6 ? "focus" : "prefetch" }} />
          </button>
        </li>
      {/each}
    </ul>
  {:else if count === 0}
    <p class="note">This book has no pages.</p>
  {/if}
</div>

<style>
  .book { width: 100%; height: 100%; overflow-y: auto; padding: var(--s-4); align-self: start; background: var(--bg); box-sizing: border-box; }
  .hero { display: flex; flex-direction: column; align-items: center; gap: var(--s-4); text-align: center; }
  .cover { width: 200px; max-width: 60%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: var(--r-md); background: var(--surface); }
  .info { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); min-width: 0; }
  .title { margin: 0; font-size: var(--t-20); line-height: 1.25; }
  .actions { display: flex; gap: var(--s-2); flex-wrap: wrap; justify-content: center; margin-top: var(--s-2); }
  .ib { min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line-strong); border-radius: var(--r-md); background: transparent; color: var(--text); cursor: pointer; font: inherit; }
  .ib:disabled { opacity: .5; cursor: default; }
  .btn { min-height: 44px; display: inline-flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-4); border: 1px solid var(--line-strong); border-radius: var(--r-md); background: transparent; color: var(--text); font: inherit; cursor: pointer; }
  .btn.primary { background: #fff; color: #111; border-color: #fff; font-weight: 600; }
  .ib:focus-visible, .btn:focus-visible, .thumb:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .grid { list-style: none; margin: var(--s-5) 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: var(--s-2); }
  .thumb { display: block; width: 100%; padding: 0; aspect-ratio: 2 / 3; background: var(--surface); border-radius: var(--r-sm); overflow: hidden; border: 2px solid transparent; cursor: pointer; }
  .thumb.last { border-color: var(--progress); }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .note { text-align: center; color: var(--muted); padding: var(--s-5) 0; }
  @media (min-width: 900px) {
    .hero { flex-direction: row; align-items: flex-start; text-align: left; }
    .cover { max-width: none; flex: none; }
    .info { align-items: flex-start; }
    .actions { justify-content: flex-start; }
  }
</style>
