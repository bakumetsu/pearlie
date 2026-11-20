<script lang="ts">
  import type { Api, LibraryItemDetail } from "../api/client";
  import { isCompleted } from "../reader/pages";
  import BookPage from "../book/BookPage.svelte";
  import PageGrid from "../book/PageGrid.svelte";
  import Icon from "../components/Icon.svelte";
  import RatingStars from "./RatingStars.svelte";
  import StumpBookSide from "./StumpBookSide.svelte";

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
  // It holds only while the server value is the one it was set against: newer progress wins.
  let marked = $state<{ id: string; page: number; base: number | null } | null>(null);
  const readPage = $derived(
    marked && marked.id === detail.id && marked.base === (detail.read_page ?? null) ? marked.page : (detail.read_page ?? null),
  );
  const count = $derived(detail.page_count ?? 0);
  const done = $derived(isCompleted(readPage ?? 0, count));
  const last = $derived(readPage && readPage > 1 && !done ? readPage : null);
  const hasNav = $derived(!!onprev && !!onnext);

  let banOpen = $state(false);
  function reject(tag: string) {
    banOpen = false;
    onrejecttag?.(tag);
  }

  let busy = $state(false);
  async function markRead() {
    if (busy || count < 1) return;
    busy = true;
    try {
      await api.saveProgress(detail.id, count);
      marked = { id: detail.id, page: count, base: detail.read_page ?? null };
    } catch {
      onerror("Could not mark this book as read");
    } finally {
      busy = false;
    }
  }

  async function markUnread() {
    if (busy) return;
    busy = true;
    try {
      await api.saveProgress(detail.id, 0);
      marked = { id: detail.id, page: 0, base: detail.read_page ?? null };
    } catch {
      onerror("Could not mark this book as unread");
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
  by={detail.author || detail.studio || ""}
  {onback}
>
  {#snippet meta()}
    <RatingStars value={detail.rating ?? null} {onrate} size={24} />
  {/snippet}
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
      <button class="mi" role="menuitem" type="button" disabled={!readPage || busy} onclick={markUnread}>
        <Icon name="rotate-ccw" size={20} />Mark unread
      </button>
    {/if}
    <button class="mi" role="menuitem" type="button" onclick={onfavorite}>
      <Icon name={detail.favorite ? "heart-filled" : "heart"} size={20} />{detail.favorite ? "Unfavorite" : "Favorite"}
    </button>
    {#if onrejecttag}
      <button class="mi" role="menuitem" type="button" aria-expanded={banOpen} onclick={() => (banOpen = !banOpen)}><Icon name="ban" size={20} />Reject a tag</button>
    {/if}
    <button class="mi" role="menuitem" type="button" onclick={ondelete}>
      <Icon name="trash" size={20} />Delete
    </button>
  {/snippet}
  {#snippet side()}
    <StumpBookSide {detail} {tags} {onaddtag} {onremovetag} />
  {/snippet}

  {#if banOpen}
    <div class="ban" role="group" aria-label="Reject a tag">
      {#each tags as t (t)}
        <button type="button" class="chip" onclick={() => reject(t)}>{t}</button>
      {/each}
    </div>
  {/if}
  {#if count > 0 && detail.page_thumb_url}
    <PageGrid thumbTpl={detail.page_thumb_url} {count} {last} onopen={(n) => onread(n)} />
  {:else if count === 0}
    <p class="note">This book has no pages.</p>
  {/if}
</BookPage>

<style>
  .ban { display: flex; flex-wrap: wrap; gap: var(--s-1); margin-bottom: var(--s-3); }
  .chip { min-height: 44px; padding: 0 var(--s-3); border: 1px solid var(--line-strong); border-radius: 999px; background: transparent; color: var(--text); font: inherit; cursor: pointer; }
  .note { text-align: center; color: var(--muted); padding: var(--s-5) 0; }
</style>
