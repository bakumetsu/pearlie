<script lang="ts">
  import type { LibraryItem, LibraryItemDetail } from "../api/client";
  import BookPage from "../book/BookPage.svelte";
  import Icon from "../components/Icon.svelte";
  import KomgaBookSide from "./KomgaBookSide.svelte";
  import SeriesGrid from "./SeriesGrid.svelte";
  import { pickContinue, seriesRatio } from "./seriesProgress";

  let {
    detail,
    tags,
    backdropStrength = 1,
    onback,
    onopen,
    onfavorite,
    ondelete,
    onrate,
    onaddtag,
    onremovetag,
    onrejecttag,
  }: {
    detail: LibraryItemDetail;
    tags: string[];
    backdropStrength?: number;
    onback: () => void;
    onopen: (book: LibraryItem) => void;
    onfavorite: () => void;
    ondelete: () => void;
    onrate: (n: number) => void;
    onaddtag: (text: string) => void;
    onremovetag: (tag: string) => void;
    onrejecttag?: (tag: string) => void;
  } = $props();

  const books = $derived(detail.books ?? []);
  const next = $derived(pickContinue(books));
  // Continue only when something was read and an unfinished book is left; otherwise Read opens book 1.
  const resume = $derived((detail.read_count ?? 0) > 0 && next !== null);
  const target = $derived(resume ? next : (books[0] ?? null));
  const chips = $derived([...(detail.tags ?? []).slice(0, 2).map((t) => t.name), ...(detail.studio ? [detail.studio] : [])]);
</script>

<BookPage
  cover={detail.thumb_url}
  backdrop={detail.thumb_url}
  {backdropStrength}
  title={detail.title}
  sub={chips}
  progress={seriesRatio(detail.read_count, detail.book_count)}
  {onback}
>
  {#snippet read()}
    {#if target}
      <button class="btn primary" type="button" onclick={() => onopen(target)}>
        <Icon name="book" size={20} />{resume ? "Continue" : "Read"}
      </button>
    {/if}
  {/snippet}
  {#snippet actions()}
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

  {#if detail.notice}<p class="notice" role="status">{detail.notice.message}</p>{/if}
  <SeriesGrid {books} {onopen} />
</BookPage>

<style>
  .notice { margin: var(--s-3) 0 0; font-size: var(--t-14); color: var(--muted); }
</style>
