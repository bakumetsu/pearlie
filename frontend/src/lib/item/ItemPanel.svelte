<script lang="ts">
  import type { LibraryItemDetail } from "../api/client";
  import { formatTime } from "../player/geometry";
  import RatingStars from "./RatingStars.svelte";
  import TagEditor from "./TagEditor.svelte";

  let { detail, tags, onrate, onaddtag, onremovetag, onrejecttag }: {
    detail: LibraryItemDetail;
    tags: string[];
    onrate: (n: number) => void;
    onaddtag: (text: string) => void;
    onremovetag: (tag: string) => void;
    onrejecttag?: (tag: string) => void;
  } = $props();

  type Row = { dt: string; dd: string };

  const rows = $derived<Row[]>((() => {
    const r: Row[] = [];
    if (typeof detail.width === "number" && typeof detail.height === "number") {
      r.push({ dt: "Dimensions", dd: `${detail.width} × ${detail.height}` });
    }
    if (typeof detail.duration_s === "number") {
      r.push({ dt: "Duration", dd: formatTime(detail.duration_s) });
    }
    if (typeof detail.page_count === "number") {
      r.push({ dt: "Pages", dd: String(detail.page_count) });
    }
    if (typeof detail.book_count === "number") {
      const dd =
        typeof detail.read_count === "number"
          ? `${detail.book_count} (Read ${detail.read_count})`
          : String(detail.book_count);
      r.push({ dt: "Books", dd });
    }
    r.push({ dt: "Added", dd: new Date(detail.added_at).toLocaleDateString() });
    if (detail.source_url_text) {
      r.push({ dt: "Source", dd: detail.source_url_text });
    }
    return r;
  })());
</script>

<div class="panel">
  <h1 class="title">{detail.title}</h1>

  <p class="label">Rating</p>
  <RatingStars value={detail.rating ?? null} onrate={onrate} />

  <p class="label">Tags</p>
  <TagEditor tags={tags} onadd={onaddtag} onremove={onremovetag} onreject={onrejecttag} />

  <dl class="details">
    {#each rows as row (row.dt)}
      <dt>{row.dt}</dt>
      <dd>{row.dd}</dd>
    {/each}
  </dl>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--s-4);
  }
  .title {
    font-size: var(--t-20);
    color: var(--text);
    margin: 0;
  }
  .label {
    font-size: var(--t-12);
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0;
  }
  .details {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--s-2) var(--s-3);
    margin: 0;
  }
  .details dt {
    color: var(--muted);
    font-size: var(--t-14);
  }
  .details dd {
    color: var(--text);
    font-size: var(--t-14);
    margin: 0;
  }
</style>
