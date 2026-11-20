<script lang="ts">
  import type { LibraryItemDetail } from "../api/client";
  import { getRouter } from "../ctx";
  import { tagSearchHref } from "../query";
  import TagChips from "./TagChips.svelte";
  import SidePanel from "./SidePanel.svelte";
  import { itemHref } from "./kinds";

  let { detail, tags, onaddtag, onremovetag }: {
    detail: LibraryItemDetail;
    tags: string[];
    onaddtag: (text: string) => void;
    onremovetag: (tag: string) => void;
  } = $props();

  const router = getRouter();
  const isSeries = $derived(detail.kind === "series");
  const own = $derived(tags.map((name) => ({ name })));
  const inherited = $derived(isSeries ? (detail.inherited_tags ?? []).map((t) => ({ name: t.name })) : []);
  // Stump rows open the Stump page, never /web/.
  const openRow = (r: { id: string }) => router.navigate(itemHref({ kind: "book", id: r.id }));
</script>

<div class="kside">
  <section>
    <h2>Tags{#if isSeries}<em>lock = from the books</em>{/if}</h2>
    <TagChips
      tags={own}
      {inherited}
      mode="remove"
      onsearch={(name) => router.navigate(tagSearchHref(name, "books"))}
      onx={(name) => onremovetag(name)}
      onadd={onaddtag}
    />
  </section>
  <SidePanel
    source="stump"
    id={detail.id}
    kind={isSeries ? "series" : "book"}
    randomLimit={4}
    onopen={openRow}
  />
</div>

<style>
  .kside { display: flex; flex-direction: column; gap: var(--s-4); min-width: 0; }
  h2 { margin: 0 0 var(--s-1); font-size: var(--t-12); text-transform: uppercase; color: var(--muted); letter-spacing: .04em; font-weight: 500; }
  h2 em { font-style: normal; text-transform: none; letter-spacing: 0; margin-left: 6px; }
</style>
