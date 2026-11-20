<script lang="ts">
  import type { LibraryItem, LibraryItemDetail } from "../api/client";
  import BookPage from "../book/BookPage.svelte";
  import Icon from "../components/Icon.svelte";
  import StumpBookSide from "./StumpBookSide.svelte";
  import SeriesGrid from "./SeriesGrid.svelte";
  import RatingStars from "./RatingStars.svelte";
  import { pickContinue } from "./seriesProgress";

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
  } = $props();

  const books = $derived(detail.books ?? []);
  const next = $derived(pickContinue(books));
  // Continue only when something was read (a finished or a partly read book) and an unfinished book is left; otherwise Read opens book 1.
  const resume = $derived(next !== null && books.some((b) => (b.read_page ?? 0) > 0));
  const target = $derived(resume ? next : (books[0] ?? null));

  const VIEW_KEY = "pearlie.series.view";
  function loadView(): "grid" | "list" {
    try {
      return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid";
    } catch {
      return "grid";
    }
  }
  let view = $state<"grid" | "list">(loadView());
  function toggleView(): void {
    view = view === "grid" ? "list" : "grid";
    try {
      localStorage.setItem(VIEW_KEY, view);
    } catch {
      // Not saved: the choice still holds for this visit.
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
  {#snippet tools()}
    <button class="ib" type="button" aria-label={view === "grid" ? "Switch to list view" : "Switch to grid view"} title={view === "grid" ? "List view" : "Grid view"} onclick={toggleView}>
      <Icon name={view === "grid" ? "list" : "grid"} size={20} />
    </button>
  {/snippet}
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
    <StumpBookSide {detail} {tags} {onaddtag} {onremovetag} />
  {/snippet}

  {#if detail.notice}<p class="notice" role="status">{detail.notice.message}</p>{/if}
  <SeriesGrid {books} {view} continueId={resume && next ? next.id : null} {onopen} />
</BookPage>

<style>
  .notice { margin: var(--s-3) 0 0; font-size: var(--t-14); color: var(--muted); }
</style>
