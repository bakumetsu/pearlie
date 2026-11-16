<script lang="ts">
  import type { Api, LibraryItemDetail } from "../api/client";
  import { isCompleted } from "../reader/pages";
  import BookPage from "../book/BookPage.svelte";
  import PageGrid from "../book/PageGrid.svelte";
  import Icon from "../components/Icon.svelte";
  import KomgaBookSide from "./KomgaBookSide.svelte";

  let {
    detail,
    api,
    tags,
    backdropStrength = 1,
    canPrev = false,
    canNext = false,
    onback,
    onprev,
    onnext,
    onread,
    onerror,
    onfavorite,
    ondelete,
    onrate,
    onaddtag,
    onremovetag,
    onrejecttag,
  }: {
    detail: LibraryItemDetail;
    api: Pick<Api, "saveProgress">;
    tags: string[];
    backdropStrength?: number;
    canPrev?: boolean;
    canNext?: boolean;
    onback: () => void;
    // The prev/next buttons show only when onprev and onnext are passed (the item came from a list).
    onprev?: () => void;
    onnext?: () => void;
    onread: (page?: number) => void;
    onerror: (message: string) => void;
    onfavorite: () => void;
    ondelete: () => void;
    onrate: (n: number) => void;
    onaddtag: (text: string) => void;
    onremovetag: (tag: string) => void;
    onrejecttag?: (tag: string) => void;
  } = $props();

  // Local copy of the read page: mark read updates it without a reload.
  let marked = $state<{ id: string; page: number } | null>(null);
  const readPage = $derived(marked && marked.id === detail.id ? marked.page : (detail.read_page ?? null));
  const count = $derived(detail.page_count ?? 0);
  const done = $derived(isCompleted(readPage ?? 0, count));
  const last = $derived(readPage && readPage > 1 && !done ? readPage : null);
  const hasNav = $derived(!!onprev && !!onnext);

  let busy = $state(false);
  async function markRead() {
    if (busy || count < 1) return;
    busy = true;
    try {
      await api.saveProgress(detail.id, count);
      marked = { id: detail.id, page: count };
    } catch {
      onerror("Could not mark this book as read");
    } finally {
      busy = false;
    }
  }
</script>

<BookPage
  cover={detail.thumb_url}
  backdrop={detail.thumb_url}
  {backdropStrength}
  title={detail.title}
  {onback}
>
  {#snippet bar()}
    {#if hasNav}
      <button class="ib" type="button" aria-label="Previous item" title="Previous item" disabled={!canPrev} onclick={onprev}><Icon name="chevron-left" size={20} /></button>
      <button class="ib" type="button" aria-label="Next item" title="Next item" disabled={!canNext} onclick={onnext}><Icon name="chevron-right" size={20} /></button>
    {/if}
  {/snippet}
  {#snippet read()}
    {#if count > 0}
      <button class="btn primary" type="button" onclick={() => onread()}>
        <Icon name="book" size={20} />{last ? "Continue" : "Read"}
      </button>
    {/if}
  {/snippet}
  {#snippet actions()}
    {#if count > 0}
      <button class="mi" role="menuitem" type="button" disabled={done || busy} onclick={markRead}>
        <Icon name="check" size={20} />{done ? "Read" : "Mark read"}
      </button>
    {/if}
    <button class="mi" role="menuitem" type="button" onclick={onfavorite}>
      <Icon name={detail.favorite ? "heart-filled" : "heart"} size={20} />{detail.favorite ? "Unfavorite" : "Favorite"}
    </button>
    <button class="mi" role="menuitem" type="button" onclick={ondelete}>
      <Icon name="trash" size={20} />Delete
    </button>
  {/snippet}
  {#snippet side()}
    <KomgaBookSide {detail} {tags} {onrate} {onaddtag} {onremovetag} {onrejecttag} />
  {/snippet}

  {#if count > 0 && detail.page_thumb_url}
    <PageGrid thumbTpl={detail.page_thumb_url} {count} {last} onopen={(n) => onread(n)} />
  {:else if count === 0}
    <p class="note">This book has no pages.</p>
  {/if}
</BookPage>

<style>
  .note { text-align: center; color: var(--muted); padding: var(--s-5) 0; }
</style>
