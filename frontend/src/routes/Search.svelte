<script lang="ts">
  import { onMount, tick } from "svelte";
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { itemHref, toPlural } from "../lib/item/kinds";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { createSearch } from "../lib/stores/search.svelte";
  import { options } from "../lib/stores/options.svelte";
  import { visibleInSafeMode } from "../lib/stores/safeFilter";
  import { parseSearchParams, buildSearchParams, serialiseQuery, filterChips, effectiveSites, orderedSites, SITE_ORDER, DEFAULT_SITES } from "../lib/query";
  import type { SearchState, SiteId } from "../lib/query";
  import { hrefOf, linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import type { WebItem } from "../lib/api/client";
  import Icon from "../lib/components/Icon.svelte";
  import ChipField from "../lib/components/ChipField.svelte";
  import SiteMarks from "../lib/components/SiteMarks.svelte";
  import FilterPanel from "../lib/components/FilterPanel.svelte";
  import SectionRow from "../lib/components/SectionRow.svelte";
  import Tile from "../lib/components/Tile.svelte";
  import Lightbox from "../lib/components/Lightbox.svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const search = createSearch(api);

  const hidden = $derived(options.values?.hidden_sites ?? []);
  // The address keeps the saved sites; a hidden one is only left out of what is shown and searched.
  const saved = $derived(parseSearchParams("?" + match.query.toString()));
  // The saved site order sets the order of the site rows; the address keeps the fixed order.
  const siteOrder = $derived(orderedSites(options.values?.site_order));
  const query = $derived({
    ...saved,
    sites: siteOrder.filter((id) => effectiveSites(saved.sites, hidden).includes(id)),
  });

  // Chip edits stay in a draft until the user runs the search.
  let draftChips = $derived(query.chips);
  const dirty = $derived(serialiseQuery(draftChips) !== serialiseQuery(query.chips));

  let first = true;
  $effect(() => {
    search.run(query, { immediate: first });
    first = false;
  });

  let h1: HTMLHeadingElement | undefined;
  // Phone portrait pins the field row at the bottom; landscape (short height) pins it at the top.
  let phone = $state(false);
  let landscape = $state(false);
  onMount(() => {
    h1?.focus();
    const off: (() => void)[] = [];
    if (typeof window.matchMedia === "function") {
      const watch = (q: string, set: (v: boolean) => void) => {
        const mq = window.matchMedia(q);
        set(mq.matches);
        const on = (e: { matches: boolean }) => set(e.matches);
        mq.addEventListener("change", on);
        off.push(() => mq.removeEventListener("change", on));
      };
      watch("(max-width: 719px)", (v) => (phone = v));
      watch("(max-height: 500px)", (v) => (landscape = v));
    }
    return () => {
      off.forEach((f) => f());
      search.cancel();
    };
  });

  let filterOpen = $state(false);
  let fibEl: HTMLButtonElement | undefined;

  function closeFilters(): void {
    filterOpen = false;
    void tick().then(() => fibEl?.focus());
  }
  const chips = $derived(filterChips(query));

  function navigateState(next: SearchState): void {
    router.navigate("/" + buildSearchParams(next), { replace: true });
  }

  function handleChipsChange(chips: typeof query.chips): void {
    draftChips = chips;
  }

  function runSearch(): void {
    if (dirty) navigateState({ ...saved, chips: draftChips });
  }

  function handlePillChange(pill: typeof query.pill): void {
    navigateState({ ...saved, pill });
  }

  function clearFilters(): void {
    navigateState({ ...saved, pill: "all", sites: DEFAULT_SITES });
  }

  function handleSitesChange(sites: SiteId[]): void {
    const kept = sites.length ? saved.sites.filter((id) => hidden.includes(id)) : [];
    navigateState({ ...saved, sites: SITE_ORDER.map((d) => d.id).filter((id) => kept.includes(id) || sites.includes(id)) });
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

  const noResults = $derived(
    Object.keys(search.sections).length > 0 &&
      Object.values(search.sections).every(
        (entry) =>
          entry.status === "done" &&
          (!entry.section || (entry.section as { items?: unknown[] }).items?.length === 0)
      )
  );

  // The nhentai row is pinned first; the other rows keep their order.
  const orderedSections = $derived.by(() => {
    const all = Object.entries(search.sections);
    return [...all.filter(([id]) => id === "nhentai"), ...all.filter(([id]) => id !== "nhentai")];
  });

  const SKELETONS = Array.from({ length: 6 }, (_, i) => i);
</script>

<div class="page" class:phone={phone && !landscape} class:landscape>
  <header class="header">
    <h1 class="sr-only" tabindex="-1" bind:this={h1}>Discover</h1>
    <div class="hmarks">
      <SiteMarks sites={query.sites} onsites={handleSitesChange} {hidden} order={siteOrder} onreorder={(o) => options.set({ site_order: o })} />
    </div>
    <div class="hfield">
      <div class="search-row">
        <ChipField chips={draftChips} onchange={handleChipsChange} onsubmit={runSearch}>
          {#snippet trailing()}
            <button
              class="fib"
              bind:this={fibEl}
              class:on={chips.length > 0}
              type="button"
              aria-label={chips.length ? `Filters (${chips.length} set)` : "Filters"}
              aria-expanded={filterOpen}
              onclick={() => (filterOpen = true)}
            >
              <Icon name="sliders" size={20} />
              {#if chips.length}<b>{chips.length}</b>{/if}
            </button>
          {/snippet}
        </ChipField>
        {#if dirty}
          <button class="search-btn" type="button" aria-label="Search" onclick={runSearch}>
            <Icon name="search" size={20} />
          </button>
        {/if}
      </div>
    </div>
    {#if chips.length}
      <div class="hchips" role="group" aria-label="Active filters">
        {#each chips as c (c.key)}
          <span class="fchip">
            {c.label}
            <button type="button" aria-label="Remove {c.label}" onclick={() => navigateState({ ...query, ...c.remove })}>
              <Icon name="x" size={14} />
            </button>
          </span>
        {/each}
      </div>
    {/if}
  </header>

  <main class="content">
    {#if search.banner}
      <div class="banner" role="alert">
        <span>Search failed</span>
        <button class="banner-btn" onclick={() => search.retryAll()}>Retry</button>
      </div>
    {/if}

    {#each orderedSections as [id, entry] (id)}
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
          wide={id === "stash_videos"}
          onretry={() => search.retrySection(id)}
          onnavigate={(e) => linkClick(e, router)}
        >
          {#each visibleInSafeMode(entry.section?.items ?? []) as item (("post_id" in item) ? item.source + ":" + item.post_id : item.kind + ":" + item.id)}{#if "post_id" in item}<Tile item={item} saveState={tileSaveState(item)} savedHref={tileSavedHref(item)} onsave={() => doSave(item)} onopen={() => (lightbox = item)} />{:else}<Tile item={item} href={itemHref(item)} landscape={id === "stash_videos"} onnavigate={(e) => linkClick(e, router)} />{/if}{/each}
        </SectionRow>
      {/if}
    {/each}

    {#if noResults}
      <div class="no-results">
        <p>No results</p>
        <p class="hint">Remove a tag or add a source.</p>
      </div>
    {/if}
  </main>
</div>

{#if filterOpen}
  <FilterPanel
    pill={query.pill}
    sites={query.sites}
    onpill={handlePillChange}
    onsites={handleSitesChange}
    onclear={clearFilters}
    onclose={closeFilters}
  />
{/if}

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

  .search-row {
    display: flex;
    align-items: stretch;
    gap: var(--s-2);
  }

  .search-row :global(.field) {
    flex: 1;
    min-width: 0;
  }

  .fib {
    position: relative;
    display: grid;
    place-items: center;
    flex: none;
    margin-left: auto;
    width: 44px;
    height: 44px;
    margin-block: -8px;
    padding: 0;
    background: none;
    border: none;
    border-radius: var(--r-md);
    color: var(--muted);
    cursor: pointer;
  }

  .fib:hover {
    color: var(--text);
  }

  .fib.on {
    color: var(--accent);
  }

  .fib b {
    position: absolute;
    top: 5px;
    right: 3px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 8px;
    background: var(--accent);
    color: var(--bg);
    font-size: 10px;
    display: grid;
    place-items: center;
  }

  .hchips {
    display: flex;
    gap: var(--s-1);
    overflow-x: auto;
    scrollbar-width: none;
    align-items: center;
    padding-block: 4px;
  }

  .fchip {
    display: inline-flex;
    flex: none;
    align-items: center;
    min-height: 36px;
    padding: 0 4px 0 12px;
    border-radius: 18px;
    background: var(--accent-bg);
    color: var(--accent);
    font-size: var(--t-13);
    white-space: nowrap;
  }

  .fchip button {
    display: grid;
    place-items: center;
    min-width: 44px;
    min-height: 44px;
    margin-block: -4px;
    padding: 0;
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
  }

  /* Phone portrait: only the field row is pinned, at the bottom. Landscape: pinned at the top. */
  .page.phone .header,
  .page.landscape .header {
    display: contents;
  }

  .page.phone .hmarks,
  .page.phone .hchips,
  .page.landscape .hmarks,
  .page.landscape .hchips {
    padding: var(--s-2) var(--s-3) 0;
  }

  .page.landscape .hfield {
    position: sticky;
    top: 0;
    z-index: 100;
    background: var(--bg);
    padding: var(--s-2) var(--s-3);
    padding-right: calc(var(--s-3) + var(--sfw-inset));
    border-bottom: 1px solid var(--line);
  }

  .page.phone .hfield {
    position: fixed;
    left: var(--rail-w);
    right: 0;
    bottom: 0;
    z-index: 100;
    background: var(--bg);
    padding: var(--s-2) var(--s-3);
    padding-bottom: calc(var(--s-2) + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--line);
  }

  .page.phone .content {
    padding-bottom: calc(88px + env(safe-area-inset-bottom, 0px));
  }

  .search-btn {
    flex: 0 0 44px;
    display: grid;
    place-items: center;
    width: 44px;
    min-height: 44px;
    padding: 0;
    background: var(--accent);
    color: var(--surface);
    border: none;
    border-radius: var(--r-lg);
    cursor: pointer;
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
