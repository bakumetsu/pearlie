<script lang="ts">
  import { onMount } from "svelte";
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { itemHref, toPlural } from "../lib/item/kinds";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { createSearch } from "../lib/stores/search.svelte";
  import { parseSearchParams, buildSearchParams, serialiseQuery, sectionsFor, webNeedsQuery } from "../lib/query";
  import type { SearchState, SectionId, SiteId } from "../lib/query";
  import { hrefOf, linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import type { WebItem } from "../lib/api/client";
  import ChipField from "../lib/components/ChipField.svelte";
  import PillBar from "../lib/components/PillBar.svelte";
  import SectionRow from "../lib/components/SectionRow.svelte";
  import Tile from "../lib/components/Tile.svelte";
  import Lightbox from "../lib/components/Lightbox.svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const search = createSearch(api);

  const WEB_IDS: SectionId[] = ["danbooru", "gelbooru", "rule34", "nhentai"];
  const SITE_NAMES: Record<SiteId, string> = {
    danbooru: "Danbooru",
    gelbooru: "Gelbooru",
    rule34: "Rule34",
    nhentai: "nhentai",
  };

  const query = $derived(parseSearchParams("?" + match.query.toString()));

  let first = true;
  $effect(() => {
    search.run(query, { immediate: first });
    first = false;
    return () => search.cancel();
  });

  let h1: HTMLHeadingElement | undefined;
  onMount(() => {
    h1?.focus();
  });

  function navigateState(next: SearchState): void {
    router.navigate("/" + buildSearchParams(next), { replace: true });
  }

  function handleChipsChange(chips: typeof query.chips): void {
    navigateState({ ...query, chips });
  }

  function handlePillChange(pill: typeof query.pill): void {
    navigateState({ ...query, pill });
  }

  function handleSitesChange(sites: SiteId[]): void {
    navigateState({ ...query, sites });
  }

  function tileSaveState(item: WebItem): "idle" | "queued" | "in_library" {
    const s = search.saveStateOf(item)?.state;
    if (s === "queued") return "queued";
    if (s === "in_library") return "in_library";
    return "idle";
  }

  function tileSavedHref(item: WebItem): string | undefined {
    const ss = search.saveStateOf(item);
    if (ss?.state === "in_library") {
      if (ss.ref) return `/item/${toPlural(ss.ref.kind) ?? ss.ref.kind}/${ss.ref.id}`;
      const saved = (item as Record<string, unknown>).saved;
      if (saved && typeof saved === "object" && "kind" in saved && "id" in saved) {
        const ref = saved as { kind: string; id: string };
        return `/item/${toPlural(ref.kind) ?? ref.kind}/${ref.id}`;
      }
    }
    const saved = (item as Record<string, unknown>).saved;
    if (saved && typeof saved === "object" && "kind" in saved && "id" in saved) {
      const ref = saved as { kind: string; id: string };
      return `/item/${toPlural(ref.kind) ?? ref.kind}/${ref.id}`;
    }
    return undefined;
  }

  let lightbox: WebItem | null = $state(null);

  const lightboxSaveState = $derived(
    lightbox ? (search.saveStateOf(lightbox)?.state ?? "idle") : "idle"
  );
  const lightboxSavedHref = $derived(
    lightbox ? tileSavedHref(lightbox) : undefined
  );

  async function doSave(item: WebItem): Promise<void> {
    const r = await search.save(item);
    switch (r.result) {
      case "queued":
        toasts.push({ kind: "info", message: "Added to queue", actionLabel: "View", href: "/queue" });
        break;
      case "in_library":
        break;
      case "blocked":
        toasts.push({ kind: "error", message: "Blocked by a rule" });
        break;
      case "error":
        toasts.push({ kind: "error", message: "Could not save. Try again." });
        break;
    }
  }

  const webSitesToHint = $derived(
    webNeedsQuery(query)
      ? sectionsFor(query.pill, query.sites).filter(
          (id): id is SiteId =>
            (WEB_IDS as string[]).includes(id) && !(id in search.sections)
        )
      : []
  );

  const noResults = $derived(
    Object.keys(search.sections).length > 0 &&
      Object.values(search.sections).every(
        (entry) =>
          entry.status === "done" &&
          (!entry.section || (entry.section as { items?: unknown[] }).items?.length === 0)
      )
  );

  const SKELETONS = Array.from({ length: 6 }, (_, i) => i);
</script>

<div class="page">
  <header class="header">
    <h1 class="sr-only" tabindex="-1" bind:this={h1}>Discover</h1>
    <ChipField chips={query.chips} onchange={handleChipsChange} />
    <PillBar
      pill={query.pill}
      sites={query.sites}
      onpill={handlePillChange}
      onsites={handleSitesChange}
    />
  </header>

  <main class="content">
    {#if search.banner}
      <div class="banner" role="alert">
        <span>Search failed</span>
        <button class="banner-btn" onclick={() => search.retryAll()}>Retry</button>
      </div>
    {/if}

    {#each Object.entries(search.sections) as [id, entry] (id)}
      {#if entry.status === "loading"}
        <div class="skeleton-row">
          <div class="skeleton-title"></div>
          <div class="skeleton-items">
            {#each SKELETONS as s (s)}
              <div class="skeleton"></div>
            {/each}
          </div>
        </div>
      {:else if entry.status === "error" || (entry.section && (entry.section as { items?: unknown[] }).items?.length)}
        <SectionRow
          title={(entry.section as { title?: string })?.title ?? id}
          count={(entry.section as { total?: number })?.total}
          seeAllHref={id === "komga_books" ? hrefOf("/library/komga/series") : hrefOf("/see-all", { source: id, q: serialiseQuery(query.chips) })}
          hidden={(entry.section as { hidden?: number })?.hidden}
          rulesHref="/rules"
          error={entry.error}
          onretry={() => search.retrySection(id)}
          onnavigate={(e) => linkClick(e, router)}
        >
          {#each (entry.section?.items ?? []) as item (("post_id" in item) ? item.source + ":" + item.post_id : item.kind + ":" + item.id)}{#if "post_id" in item}<Tile item={item} saveState={tileSaveState(item)} savedHref={tileSavedHref(item)} onsave={() => doSave(item)} onopen={() => (lightbox = item)} />{:else}<Tile item={item} href={itemHref(item)} onnavigate={(e) => linkClick(e, router)} />{/if}{/each}
        </SectionRow>
      {/if}
    {/each}

    {#each webSitesToHint as site (site)}
      <div class="web-hint">
        <h2>{SITE_NAMES[site]}</h2>
        <p>Type a tag to search the web</p>
      </div>
    {/each}

    {#if noResults}
      <div class="no-results">
        <p>No results</p>
        <p class="hint">Remove a tag or add a source.</p>
      </div>
    {/if}
  </main>
</div>

{#if lightbox}
  <Lightbox
    item={lightbox}
    saveState={lightboxSaveState}
    savedHref={lightboxSavedHref}
    onsave={() => { if (lightbox) doSave(lightbox); }}
    onclose={() => (lightbox = null)}
  />
{/if}

<style>
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }

  .page {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .header {
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 100;
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    padding: var(--s-3) var(--s-4);
    padding-right: calc(var(--s-4) + var(--sfw-inset));
    border-bottom: 1px solid var(--line);
  }

  .content {
    flex: 1;
    width: 100%;
    max-width: var(--content-max);
    margin: 0 auto;
    padding: var(--s-4);
    display: flex;
    flex-direction: column;
    gap: var(--s-5);
  }

  .banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--s-3);
    background: var(--danger-bg);
    border-radius: var(--r-md);
    color: var(--danger-fg);
    font-size: var(--t-14);
  }

  .banner-btn {
    padding: var(--s-1) var(--s-3);
    background: var(--danger-fg);
    color: var(--surface);
    border: none;
    border-radius: var(--r-sm);
    font-size: var(--t-13);
    cursor: pointer;
  }

  .skeleton-row {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }

  .skeleton-title {
    width: 120px;
    height: 24px;
    border-radius: var(--r-sm);
    background: var(--surface);
    animation: pulse 1.5s ease-in-out infinite;
  }

  .skeleton-items {
    display: flex;
    gap: var(--s-2);
    overflow: hidden;
  }

  .skeleton {
    flex: 0 0 160px;
    width: 160px;
    height: 160px;
    border-radius: var(--r-md);
    background: var(--surface);
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .web-hint {
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
  }

  .web-hint h2 {
    margin: 0;
    font-size: var(--t-20);
    font-weight: 600;
    color: var(--text);
  }

  .web-hint p {
    margin: 0;
    font-size: var(--t-14);
    color: var(--muted);
  }

  .no-results {
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
    padding: var(--s-5) 0;
    text-align: center;
  }

  .no-results p {
    margin: 0;
    font-size: var(--t-18);
    color: var(--text);
  }

  .no-results .hint {
    font-size: var(--t-14);
    color: var(--muted);
  }
</style>
