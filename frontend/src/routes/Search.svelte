<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import { getApi } from "../lib/api/client";
  import { getRouter, findJobs } from "../lib/ctx";
  import { itemHref, toPlural } from "../lib/item/kinds";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { createSearch } from "../lib/stores/search.svelte";
  import { createMergedRow } from "../lib/stores/mergedRow.svelte";
  import { options } from "../lib/stores/options.svelte";
  import { placement } from "../lib/stores/placement.svelte";
  import { sfw } from "../lib/stores/sfw.svelte";
  import { tappedSite, firstTapped } from "../lib/stores/tappedSite.svelte";
  import { readSites, writeSites, readAll, writeAll } from "../lib/stores/siteMemory";
  import { parseSearchParams, buildSearchParams, serialiseQuery, commitText, nhentaiIdOf, filterChips, effectiveSites, orderedSites, SITE_ORDER, DEFAULT_SITES } from "../lib/query";
  import type { SearchState, SiteId } from "../lib/query";
  import { hrefOf, linkClick, inPageClick, webItemHref } from "../lib/router";
  import { seedVideoQueue } from "../lib/item/rowQueue";
  import type { Section } from "../lib/api/client";
  import type { Match } from "../lib/router";
  import type { WebItem } from "../lib/api/client";
  import Icon from "../lib/components/Icon.svelte";
  import ChipField from "../lib/components/ChipField.svelte";
  import SiteMarks from "../lib/components/SiteMarks.svelte";
  import FilterPanel from "../lib/components/FilterPanel.svelte";
  import SectionRow from "../lib/components/SectionRow.svelte";
  import MergedRow from "../lib/components/MergedRow.svelte";
  import Tile from "../lib/components/Tile.svelte";
  import { saveWebItem } from "../lib/web/saveFlow";
  import { restoreSaved } from "../lib/web/restoreSaved";
  import Lightbox from "../lib/components/Lightbox.svelte";
  import { parseWeb, withWeb, webTileHref, fetchWebPost } from "../lib/browse/webOpen";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const search = createSearch(api);
  const mergedRow = createMergedRow(api);
  const jobsStore = findJobs();
  $effect(() => {
    if (jobsStore) search.settle(jobsStore.items);
  });

  const hidden = $derived(options.values?.hidden_sites ?? []);
  // The address keeps the saved sites; a hidden one is only left out of what is shown and searched.
  // A sites or all param in the address wins; without one, the pills last chosen on this device apply.
  // A device that remembers sites but never saw All keeps its site choice (no All).
  const saved = $derived.by(() => {
    const parsed = parseSearchParams("?" + match.query.toString());
    if (match.query.has("sites") || match.query.has("all")) return parsed;
    const sites = readSites();
    return { ...parsed, sites: sites ?? parsed.sites, all: readAll() ?? sites === undefined };
  });
  // The saved site order sets the order of the site rows; the address keeps the fixed order.
  const siteOrder = $derived(orderedSites(options.values?.site_order));
  const names = $derived(options.values?.site_names ?? true);
  const query = $derived({
    ...saved,
    sites: firstTapped(
      siteOrder.filter((id) => effectiveSites(saved.sites, hidden).includes(id)),
      tappedSite.id,
      options.values?.tapped_first ?? false,
    ),
  });

  // The merged row: All on, no query, and at least 2 rail sites (the sites not hidden in Options).
  const rail = $derived(siteOrder.filter((id) => !hidden.includes(id)));
  const mergedMode = $derived(!!query.all && query.pill === "all" && query.chips.length === 0 && rail.length >= 2);

  // Chip edits stay in a draft until the user runs the search.
  let draftChips = $derived(query.chips);
  let pending = $state("");
  const dirty = $derived(pending.trim() !== "" || serialiseQuery(draftChips) !== serialiseQuery(query.chips));

  let first = true;
  let lastSafe: boolean | undefined;
  $effect(() => {
    // The server drops the safe-mode posts, so a toggle sends the same query again.
    const safe = sfw?.on ?? false;
    const toggled = lastSafe !== undefined && safe !== lastSafe;
    lastSafe = safe;
    // The merged row has its own request: no /api/search call (no sections).
    search.run(mergedMode ? { ...query, sites: [] } : query, { immediate: first || toggled, force: toggled });
    first = false;
  });

  // The merged row loads while it shows; a pill tap away stops the wait (the backend call goes on and fills its cache).
  let lastMergedSafe: boolean | undefined;
  $effect(() => {
    const safe = sfw?.on ?? false;
    const on = mergedMode;
    const key = `merged:${rail.join(",")}:${safe ? "safe" : "open"}`;
    const toggled = lastMergedSafe !== undefined && safe !== lastMergedSafe;
    lastMergedSafe = safe;
    untrack(() => {
      if (on) mergedRow.load({ key, force: toggled });
      else mergedRow.abort();
    });
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
    writeSites(next.sites);
    writeAll(!!next.all);
    router.navigate("/" + buildSearchParams(next), { replace: true });
  }

  function handleChipsChange(chips: typeof query.chips): void {
    draftChips = chips;
  }

  // A lone book id (typed, or the only chip) opens the nhentai book page; with other chips it stays a chip.
  function bookIdNow(): string | null {
    if (draftChips.length === 0) return nhentaiIdOf(pending);
    if (draftChips.length === 1 && !pending.trim()) return nhentaiIdOf(draftChips[0].raw);
    return null;
  }

  function openBook(id: string): void {
    pending = "";
    router.navigate("/web/nhentai/" + id);
  }

  function interceptEnter(): boolean {
    const id = bookIdNow();
    if (!id) return false;
    openBook(id);
    return true;
  }

  function runSearch(): void {
    if (!dirty) return;
    const id = bookIdNow();
    if (id) return openBook(id);
    const next = pending.trim() ? commitText(draftChips, pending) : draftChips;
    pending = "";
    navigateState({ ...saved, chips: next });
  }

  function handlePillChange(pill: typeof query.pill): void {
    navigateState({ ...saved, pill });
  }

  // Build from the saved state so hidden sites stay, and keep the unsaved draft chips and pending text.
  function removeFilterChip(change: Partial<typeof query>): void {
    const draft = draftChips;
    const keep = change.sites;
    const next = keep ? { ...saved, sites: saved.sites.filter((id) => hidden.includes(id) || keep.includes(id)) } : { ...saved, ...change };
    navigateState(next);
    void tick().then(() => {
      draftChips = draft;
    });
  }

  function clearFilters(): void {
    navigateState({ ...saved, pill: "all", sites: DEFAULT_SITES, all: true });
  }

  function handleSitesChange(sites: SiteId[]): void {
    const kept = sites.length ? saved.sites.filter((id) => hidden.includes(id)) : [];
    navigateState({ ...saved, all: false, sites: SITE_ORDER.map((d) => d.id).filter((id) => kept.includes(id) || sites.includes(id)) });
  }

  // All is exclusive: the site selection shows empty and stays in memory for the next site tap.
  function handleAll(): void {
    navigateState({ ...saved, all: true });
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

  // The address names the open post (replace, no history entries); a new tab opens it from there.
  function setWebParam(key: string | null) {
    const qs = withWeb(match.query, key);
    if (qs !== match.query.toString()) router.navigate(match.path + (qs ? `?${qs}` : ""), { replace: true });
  }
  function openWeb(item: WebItem) {
    lightbox = item;
    setWebParam(item.source + ":" + item.post_id);
  }
  function closeWeb() {
    lightbox = null;
    setWebParam(null);
  }

  const rawWeb = $derived(parseWeb(match.query));
  let webTried: string | null = null;
  $effect(() => {
    const ref = rawWeb;
    if (!ref) { webTried = null; return; }
    if (search.loading || mergedRow.status === "loading") return;
    if (lightbox && lightbox.source === ref.source && lightbox.post_id === ref.postId) return;
    const hit = [...Object.values(search.sections).flatMap((e) => (e.section?.items ?? [])), ...mergedRow.items]
      .find((i): i is WebItem => "post_id" in i && i.source === ref.source && i.post_id === ref.postId);
    if (hit) { lightbox = hit; return; }
    const key = ref.source + ":" + ref.postId;
    if (webTried === key) return;
    webTried = key;
    fetchWebPost(api, ref).then((w) => {
      if (parseWeb(match.query)?.postId !== ref.postId) return;
      if (w) lightbox = w;
      else {
        toasts.push({ kind: "error", message: "Post not available" });
        setWebParam(null);
      }
    });
  });

  const lightboxSaveState = $derived(
    lightbox ? (search.saveStateOf(lightbox)?.state ?? "idle") : "idle"
  );
  const lightboxSavedHref = $derived(
    lightbox ? tileSavedHref(lightbox) : undefined
  );

  function doSave(item: WebItem): Promise<void> {
    return saveWebItem(
      { ask: (i) => placement.ask(i), save: (i, p) => search.save(i, p), toast: (t) => toasts.push(t), restore: restoreSaved({ api, navigate: (h) => router.navigate(h), toast: (t) => toasts.push(t) }) },
      item,
    );
  }

  const noResults = $derived(
    Object.keys(search.sections).length > 0 &&
      Object.values(search.sections).every(
        (entry) =>
          entry.status === "done" &&
          (!entry.section || (entry.section as { items?: unknown[] }).items?.length === 0)
      )
  );

  // The store builds the rows in query order: site rows come first in the pill order, library rows below.
  // A video tile click queues the row's loaded items; further pages load as in See all.
  function queueVideos(section: Section | null | undefined) {
    const q = serialiseQuery(query.chips);
    const pageSize = section?.page_size ?? undefined;
    seedVideoQueue(
      "row:discover:videos:" + q,
      section?.items ?? [],
      async (page, signal) => {
        const r = await api.search({ q, sources: ["stash_videos"], page, page_size: pageSize }, signal);
        const s = r.sections?.find((x: { id: string }) => x.id === "stash_videos");
        return { items: s?.items ?? [], total: s?.total ?? null, next_page: s?.next_page ?? null, pages: s?.pages ?? null, page_size: s?.page_size ?? null };
      },
      { total: section?.total ?? null, pageSize: pageSize ?? null, hasNext: section?.next_page != null },
    );
  }

  const orderedSections = $derived(Object.entries(search.sections));

  const SKELETONS = Array.from({ length: 6 }, (_, i) => i);
</script>

<div class="page" class:phone={phone && !landscape} class:landscape>
  <header class="header">
    <h1 class="sr-only" tabindex="-1" bind:this={h1}>Discover</h1>
    <div class="hmarks">
      <SiteMarks sites={mergedMode ? [] : query.sites} all={rail.length >= 2 ? mergedMode : undefined} onall={handleAll} onsites={handleSitesChange} {hidden} order={siteOrder} ontap={(id) => (tappedSite.id = id)} onreorder={(o) => options.set({ site_order: o })} {names} />
    </div>
    <div class="hfield">
      <div class="search-row">
        <ChipField bind:pending chips={draftChips} onchange={handleChipsChange} onsubmit={runSearch} intercept={interceptEnter}>
          {#snippet trailing()}
            <span class="tail">
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
            </span>
          {/snippet}
        </ChipField>
        <button class="search-btn" type="button" aria-label="Search" onclick={runSearch}>
          <Icon name="search" size={20} />
        </button>
      </div>
    </div>
    {#if chips.length}
      <div class="hchips" role="group" aria-label="Active filters">
        {#each chips as c (c.key)}
          <span class="fchip">
            {c.label}
            <button type="button" aria-label="Remove {c.label}" onclick={() => removeFilterChip(c.remove)}>
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

    {#if mergedMode}
      <MergedRow
        items={mergedRow.items}
        status={mergedRow.status}
        error={mergedRow.error}
        hidden={mergedRow.hidden}
        onretry={() => mergedRow.retry()}
        onnavigate={(e) => linkClick(e, router)}
        tileHref={(item) => webItemHref(item.source, item.post_id) ?? webTileHref(match.path, match.query, item)}
        saveState={tileSaveState}
        savedHref={tileSavedHref}
        onsave={doSave}
        onopen={(item) => { const h = webItemHref(item.source, item.post_id); if (h) router.navigate(h); else openWeb(item); }}
      />
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
          seeAllHref={id === "stump_books" ? hrefOf("/library/stump/series") : hrefOf("/see-all", { source: id, q: serialiseQuery(query.chips) })}
          hidden={(entry.section as { hidden?: number })?.hidden}
          rulesHref="/rules"
          error={entry.error}
          wide={id === "stash_videos"}
          onretry={() => search.retrySection(id)}
          onnavigate={(e) => linkClick(e, router)}
        >
          {#each (entry.section?.items ?? []) as item (("post_id" in item) ? item.source + ":" + item.post_id : item.kind + ":" + item.id)}{#if "post_id" in item}<Tile item={item} href={webItemHref(item.source, item.post_id) ?? webTileHref(match.path, match.query, item)} saveState={tileSaveState(item)} savedHref={tileSavedHref(item)} onsave={() => doSave(item)} onopen={() => { const h = webItemHref(item.source, item.post_id); if (h) router.navigate(h); else openWeb(item); }} />{:else}<Tile item={item} href={itemHref(item)} landscape={id === "stash_videos"} onnavigate={(e) => { if (id === "stash_videos" && inPageClick(e)) queueVideos(entry.section); linkClick(e, router); }} />{/if}{/each}
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
    {hidden}
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
    onclose={closeWeb}
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
    border-bottom: 1px solid var(--line);
  }

  /* Only the top row shares space with the fixed SFW toggle; the field row uses the full width. */
  .hmarks {
    padding-right: var(--sfw-inset);
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

  .tail {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--s-1);
    margin-left: auto;
    margin-block: -8px;
  }

  .fib {
    position: relative;
    display: grid;
    place-items: center;
    flex: none;
    width: 44px;
    height: 44px;
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
    min-height: 44px;
    padding: 0 4px 0 12px;
    border-radius: 22px;
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
    align-self: flex-start;
    padding: 0;
    background: var(--accent);
    color: var(--on-accent);
    border: none;
    border-radius: var(--r-lg);
    cursor: pointer;
  }

  .content {
    flex: 1;
    width: 100%;
    padding: var(--s-4) var(--gutter);
    min-width: 0;
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
    min-height: 44px;
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
