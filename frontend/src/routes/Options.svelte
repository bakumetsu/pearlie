<script lang="ts">
  import { tick, untrack } from "svelte";
  import { type Match } from "../lib/router";
  import { getRouter } from "../lib/ctx";
  import {
    SECTIONS,
    searchSections,
    type SearchHit,
    rowMatches,
    type OptionCard,
    SECTION_ICONS,
    isSectionId,
    type SectionId,
    type Section,
    type Group,
  } from "../lib/options/sections";
  import Icon from "../lib/components/Icon.svelte";
  import "../lib/options/options.css";
  import { SvelteMap } from "svelte/reactivity";
  import Rules from "./Rules.svelte";
  import ImageViewerCard from "../lib/options/ImageViewerCard.svelte";
  import ListsCard from "../lib/options/ListsCard.svelte";
  import DownloadsCard from "../lib/options/DownloadsCard.svelte";
  import StatusCard from "../lib/options/StatusCard.svelte";
  import UpdateCard from "../lib/options/UpdateCard.svelte";
  import ChangelogCard from "../lib/options/ChangelogCard.svelte";
  import LogsCard from "../lib/options/LogsCard.svelte";
  import TrashRetentionCard from "../lib/options/TrashRetentionCard.svelte";
  import SaveFoldersCard from "../lib/options/SaveFoldersCard.svelte";
  import ConnectionRows from "../lib/options/ConnectionRows.svelte";
  import ContentFilterCard from "../lib/options/ContentFilterCard.svelte";
  import DiscoverCard from "../lib/options/DiscoverCard.svelte";
  import { guardedNavigate } from "../lib/stores/rules.svelte";

  let { match }: { match: Match } = $props();

  const router = getRouter();

  // ── Responsive ──────────────────────────────────────────────
  let isPhone = $state(false);

  $effect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(max-width: 767px)");
    isPhone = mq.matches;
    const handler = (e: MediaQueryListEvent) => {
      isPhone = e.matches;
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  });

  // ── Search ──────────────────────────────────────────────────
  let searchQuery = $state("");
  let searchInput = $state<HTMLInputElement | null>(null);
  let searchResults = $derived(searchSections(searchQuery));

  // Focus search with "/" (unless already in an input/textarea)
  $effect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || isPhone) return;
      const tag = (document.activeElement?.tagName ?? "").toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      e.preventDefault();
      searchInput?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // Real cards for a hit: whole cards from the section, companions folded
  // into the card that renders them. Rules is a full page, so it stays a plain card.
  const COMPANION: Record<string, string> = { Komga: "Stash", "Log viewer": "Logging" };
  function resolveCards(hit: SearchHit): OptionCard[] {
    const out: OptionCard[] = [];
    for (const c of hit.cards) {
      const title = COMPANION[c.title] ?? c.title;
      if (out.some((x) => x.title === title)) continue;
      out.push(hit.section.cards.find((x) => x.title === title) ?? c);
    }
    return out;
  }

  // Scroll the first match into view whenever the results change.
  $effect(() => {
    if (!isSearching) return;
    void searchResults;
    tick().then(() => {
      const el =
        document.querySelector<HTMLElement>(".pane [data-row-hit]") ??
        document.querySelector<HTMLElement>(".pane [data-hit]");
      el?.scrollIntoView?.({ block: "nearest" });
    });
  });

  function onSearchKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      searchQuery = "";
      searchInput?.focus();
    }
  }

  function clearSearch() {
    searchQuery = "";
    searchInput?.focus();
  }

  // ── Active section ──────────────────────────────────────────
  const STORAGE_KEY = "pearlie.options.section";

  let remembered = $state<SectionId | null>(null);

  $effect(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      if (v && isSectionId(v)) remembered = v;
    } catch {
      /* ignore */
    }
  });

  let activeSectionId = $derived.by<SectionId>(() => {
    const p = match.params.section;
    if (p && isSectionId(p)) return p;
    if (remembered) return remembered;
    return "general";
  });

  // Persist on explicit navigation to a section
  $effect(() => {
    const p = match.params.section;
    if (p && isSectionId(p)) {
      try {
        localStorage.setItem(STORAGE_KEY, p);
      } catch {
        /* ignore */
      }
    }
  });

  // ── H1 focus on mount / section change ─────────────────────
  let h1El = $state<HTMLHeadingElement | null>(null);

  // Focus only when the section id changes, not when the h1 is re-mounted
  // (search typing toggles it) - otherwise the search input loses focus.
  let focusedSectionId: SectionId | null = null;
  $effect(() => {
    const id = activeSectionId;
    if (id === focusedSectionId) return;
    focusedSectionId = id;
    untrack(() => h1El?.focus());
  });

  // ── List keyboard nav (ArrowUp / ArrowDown) ─────────────────
  function onListKeydown(e: KeyboardEvent) {
    const container = e.currentTarget as HTMLElement;
    const items = Array.from(container.querySelectorAll<HTMLButtonElement>("button[data-section]"));
    const idx = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      (items[idx + 1] ?? items[0])?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      (items[idx - 1] ?? items[items.length - 1])?.focus();
    }
  }

  // ── Navigation helpers ──────────────────────────────────────
  function goTo(id: SectionId) {
    guardedNavigate(router, `/options/${id}`);
  }

  function backToOptions() {
    guardedNavigate(router, "/options");
  }

  // ── Grouped sections for list ───────────────────────────────
  let groups = $derived.by<[Group, Section[]][]>(() => {
    const m = new SvelteMap<Group, Section[]>();
    for (const s of SECTIONS) {
      const arr = m.get(s.group) ?? [];
      arr.push(s);
      m.set(s.group, arr);
    }
    return Array.from(m.entries());
  });

  // ── Active section object ───────────────────────────────────
  let activeSection = $derived(
    SECTIONS.find((s) => s.id === activeSectionId) ?? SECTIONS[0],
  );

  // ── Whether we are in "search mode" (non-empty query) ─────
  let isSearching = $derived(searchQuery.trim().length > 0);

  const SITE_NAMES = [
    { key: "danbooru", label: "Danbooru" },
    { key: "gelbooru", label: "Gelbooru" },
    { key: "rule34", label: "Rule34" },
    { key: "nhentai", label: "nhentai" },
  ];

  const LIBRARY_NAMES = [
    { key: "stash", label: "Stash" },
    { key: "komga", label: "Komga" },
  ];
</script>

{#snippet cardView(sectionId: SectionId, card: OptionCard, q: string)}
  {#if sectionId === "viewing" && card.title === "Image viewer"}
    <ImageViewerCard />
  {:else if sectionId === "viewing" && card.title === "Lists"}
    <ListsCard />
  {:else if sectionId === "content-filter" && card.title === "Content filter"}
    <ContentFilterCard />
  {:else if sectionId === "discover" && card.title === "Sites in the rail"}
    <DiscoverCard />
  {:else if sectionId === "sources" && card.title === "Downloads"}
    <DownloadsCard />
  {:else if sectionId === "save-folders" && card.title === "Save folders"}
    <SaveFoldersCard />
  {:else if sectionId === "trash" && card.title === "Retention"}
    <TrashRetentionCard />
  {:else if sectionId === "sources" && card.title === "Site access"}
    <ConnectionRows title="Site access" names={SITE_NAMES} />
  {:else if sectionId === "library" && card.title === "Stash"}
    <ConnectionRows title="Stash and Komga" names={LIBRARY_NAMES} />
  {:else if sectionId === "library" && card.title === "Komga"}
    <!-- shown with Stash -->
  {:else if sectionId === "library" && card.title === "Status"}
    <StatusCard />
  {:else if sectionId === "update" && card.title === "Update"}
    <UpdateCard />
  {:else if sectionId === "changelog" && card.title === "Changelog"}
    <ChangelogCard active={q === ""} />
  {:else if sectionId === "logs" && card.title === "Logging"}
    <LogsCard />
  {:else if sectionId === "logs" && card.title === "Log viewer"}
    <!-- shown with Logging -->
  {:else}
    <section class="card">
      <h2 class="card-title">{card.title}</h2>
      <dl>
        {#each card.rows as row (row.label)}
          <div class="row" class:row-hit={q !== "" && rowMatches(row, q)} data-row-hit={q !== "" && rowMatches(row, q) ? "" : undefined}>
            <dt>{row.label}</dt>
            <dd>{row.hint}</dd>
          </div>
        {/each}
      </dl>
    </section>
  {/if}
{/snippet}

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- PHONE: /options → list only                                  -->
<!-- ═══════════════════════════════════════════════════════════ -->
{#if isPhone && !match.params.section}
  <div class="options phone-list">
    <header class="phone-header">
      <h1 class="phone-title">Options</h1>
    </header>

    <div class="search-row" role="search">
      <label for="options-search" class="visually-hidden">Search options</label>
      <div class="search-wrap">
        <Icon name="search" size={18} />
        <input
          id="options-search"
          bind:this={searchInput}
          type="search"
          placeholder="Search options"
          aria-label="Search options"
          bind:value={searchQuery}
          onkeydown={onSearchKeydown}
        />
        {#if searchQuery}
          <button class="clear-btn" aria-label="Clear search" onclick={clearSearch}>
            <Icon name="x" size={16} />
          </button>
        {/if}
      </div>
    </div>

    <nav class="section-list" aria-label="Options sections">
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div role="group" onkeydown={onListKeydown}>
      {#if isSearching && searchResults.length === 0}
        <p class="no-results" role="status">Nothing found</p>
      {:else}
        {#each groups as [group, sections] (group)}
          <h2 class="group-label">{group}</h2>
          <ul role="list">
            {#each sections as s (s.id)}
              {@const hit = searchResults.find((h) => h.section.id === s.id)}
              {@const showInSearch = !isSearching || (hit !== undefined)}
              {#if showInSearch}
                <li>
                  <button
                    class={[
                      "section-row",
                      { later: s.later, active: s.id === activeSectionId },
                    ]}
                    data-section
                    aria-current={s.id === activeSectionId ? "page" : undefined}
                    onclick={() => goTo(s.id)}
                  >
                    <Icon name={SECTION_ICONS[s.id]} size={18} />
                    <span class="section-row-label">{s.title}</span>
                    {#if s.later}
                      <span class="later-tag">LATER</span>
                    {/if}
                    {#if isSearching && hit}
                      <span class="count-badge">{hit.count}</span>
                    {/if}
                  </button>
                </li>
              {/if}
            {/each}
          </ul>
        {/each}
      {/if}
      </div>
    </nav>
  </div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- PHONE: /options/<id> → section only + back                   -->
<!-- ═══════════════════════════════════════════════════════════ -->
{:else if isPhone && match.params.section}
  <div class="options phone-section">
    <header class="phone-header">
      <button
        class="back-btn"
        aria-label="Back to options"
        onclick={backToOptions}
      >
        <Icon name="arrow-left" size={20} />
      </button>
      <h1
        bind:this={h1El}
        class="phone-title"
        tabindex="-1"
      >
        {activeSection.title}
      </h1>
    </header>

    <div class="section-body">
      {#if activeSectionId === "rules"}
        <Rules />
      {:else if activeSection.later}
        <p class="coming-later">Coming later.</p>
      {:else}
        {#each activeSection.cards as card (card.title)}
          {@render cardView(activeSectionId, card, "")}
        {/each}
      {/if}
    </div>
  </div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- DESKTOP: two-pane layout                                     -->
<!-- ═══════════════════════════════════════════════════════════ -->
{:else}
  <div class="options desktop">
    <!-- Left column -->
    <aside class="sidebar">
      <div class="search-row" role="search">
        <label for="options-search-desktop" class="visually-hidden">Search options</label>
        <div class="search-wrap">
          <Icon name="search" size={18} />
          <input
            id="options-search-desktop"
            bind:this={searchInput}
            type="search"
            placeholder="Search options"
            aria-label="Search options"
            bind:value={searchQuery}
            onkeydown={onSearchKeydown}
          />
          {#if searchQuery}
            <button class="clear-btn" aria-label="Clear search" onclick={clearSearch}>
              <Icon name="x" size={16} />
            </button>
          {/if}
        </div>
      </div>

      <nav class="section-list" aria-label="Options sections">
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <div role="group" onkeydown={onListKeydown}>
        {#if isSearching && searchResults.length === 0}
          <p class="no-results" role="status">Nothing found</p>
        {:else}
          {#each groups as [group, sections] (group)}
            <h2 class="group-label">{group}</h2>
            <ul role="list">
              {#each sections as s (s.id)}
                {@const hit = searchResults.find((h) => h.section.id === s.id)}
                {@const show = !isSearching || hit !== undefined}
                {#if show}
                  <li>
                    <button
                      class={[
                        "section-row",
                        { later: s.later, active: s.id === activeSectionId },
                      ]}
                      data-section
                      aria-current={s.id === activeSectionId ? "page" : undefined}
                      onclick={() => goTo(s.id)}
                    >
                      <Icon name={SECTION_ICONS[s.id]} size={18} />
                      <span class="section-row-label">{s.title}</span>
                      {#if s.later}
                        <span class="later-tag">LATER</span>
                      {/if}
                      {#if isSearching && hit}
                        <span class="count-badge">{hit.count}</span>
                      {/if}
                    </button>
                  </li>
                {/if}
              {/each}
            </ul>
          {/each}
        {/if}
        </div>
      </nav>
    </aside>

    <!-- Right pane -->
    <div class="pane">
      {#if isSearching}
        <!-- Search results in pane -->
        <h1
          bind:this={h1El}
          class="pane-title"
          tabindex="-1"
        >
          Search results
        </h1>

        {#if searchResults.length === 0}
          <p class="no-results" role="status">Nothing found</p>
        {:else}
          {#each searchResults as hit (hit.section.id)}
            <h2 class="result-heading">{hit.section.title}</h2>
            {#each resolveCards(hit) as card (card.title)}
              <div class="hit-card" data-hit>
                {@render cardView(hit.section.id, card, searchQuery.trim().toLowerCase())}
              </div>
            {/each}
          {/each}
        {/if}
      {:else}
        <!-- Normal section view -->
        <div class="crumb">Options &rsaquo; {activeSection.title}</div>
        <h1
          bind:this={h1El}
          class="pane-title"
          tabindex="-1"
        >
          {activeSection.title}
        </h1>

        {#if activeSectionId === "rules"}
          <Rules />
        {:else if activeSection.later}
          <p class="coming-later">Coming later.</p>
        {:else}
          {#each activeSection.cards as card (card.title)}
            {@render cardView(activeSectionId, card, "")}
          {/each}
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .options {
    display: flex;
    height: 100%;
    min-height: 0;
    font-family: var(--font-sans, system-ui, sans-serif);
    color: var(--text);
  }

  /* ── Desktop two-pane ─────────────────────────────────── */
  .desktop {
    flex-direction: row;
  }

  .sidebar {
    width: 220px;
    min-width: 220px;
    border-right: 1px solid var(--line);
    overflow-y: auto;
    padding: 12px 8px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .pane {
    flex: 1;
    overflow-y: auto;
    padding: 16px 24px;
  }

  .crumb {
    font-size: var(--t-12);
    color: var(--muted);
    margin: 0 0 4px;
  }

  .pane-title {
    font-size: 18px;
    font-weight: 600;
    margin: 0 0 12px;
    outline: none;
  }

  /* ── Search ───────────────────────────────────────────── */
  .search-row {
    position: relative;
  }

  .search-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    border: 1px solid var(--line-strong);
    border-radius: var(--r-md);
    padding: 0 12px;
    min-height: 44px;
    background: var(--surface);
  }

  .search-wrap :global(svg) {
    flex: none;
  }

  .search-wrap input {
    flex: 1;
    min-width: 0;
    border: none;
    outline: none;
    font-size: 0.9rem;
    min-height: 44px;
    background: transparent;
    color: var(--text);
  }

  .search-wrap input::placeholder {
    color: var(--muted);
  }

  .clear-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    min-width: 44px;
    border: none;
    background: none;
    cursor: pointer;
    color: var(--muted);
    border-radius: 50%;
  }

  .clear-btn:hover {
    color: var(--text);
  }

  /* ── Section list ─────────────────────────────────────── */
  .section-list {
    flex: 1;
    overflow-y: auto;
  }

  .group-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin: 12px 0 4px;
    padding-left: 12px;
  }

  .section-list ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .section-row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    min-height: 44px;
    padding: 8px 12px;
    border: none;
    border-radius: var(--r-sm);
    background: none;
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--text);
    text-align: left;
    transition: background 120ms;
  }

  .section-row:hover {
    background: var(--line);
  }

  .section-row:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .section-row.active {
    background: var(--accent-bg);
    color: var(--accent);
    font-weight: 600;
  }

  .search-wrap:focus-within {
    border-color: var(--accent);
  }

  .section-row.later {
    opacity: 0.55;
  }

  .section-row-label {
    flex: 1;
  }

  .later-tag {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    border: 1px dashed var(--line-strong);
    border-radius: var(--r-sm);
    padding: 0 5px;
  }

  .count-badge {
    font-size: 0.75rem;
    color: var(--muted);
    min-width: 20px;
    text-align: center;
  }

  /* ── Placeholder cards: the shared look lives in options.css ── */
  .row dt {
    flex: 1;
    font-weight: 400;
  }

  .row dd {
    margin: 0;
    color: var(--muted);
    font-size: var(--t-13);
  }

  .coming-later {
    color: var(--muted);
    font-style: italic;
  }

  /* ── Search results in pane ───────────────────────────── */
  .hit-card {
    border-radius: var(--r-sm);
    outline: 1px solid color-mix(in srgb, var(--accent, #7aa2ff) 45%, transparent);
    outline-offset: 0;
    margin: 0 0 20px;
  }

  .hit-card :global(.card) {
    margin-bottom: 0;
  }

  .hit-card :global(.row-hit) {
    background: color-mix(in srgb, var(--accent, #7aa2ff) 14%, transparent);
    border-radius: var(--r-sm);
  }

  .result-heading {
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin: 20px 0 8px;
  }

  /* ── No results ───────────────────────────────────────── */
  .no-results {
    color: var(--muted);
    padding: 16px 12px;
    font-size: 0.9rem;
  }

  /* ── Phone: list only ─────────────────────────────────── */
  .phone-list {
    flex-direction: column;
    padding: 12px;
  }

  .phone-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0 12px;
  }

  .phone-title {
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0;
    outline: none;
  }

  /* ── Phone: section only ──────────────────────────────── */
  .phone-section {
    flex-direction: column;
    padding: 12px;
  }

  .back-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text);
    border-radius: 50%;
  }

  .back-btn:hover {
    background: var(--line);
  }

  .back-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .section-body {
    flex: 1;
    overflow-y: auto;
    padding-top: 12px;
  }

  /* ── Utility ──────────────────────────────────────────── */
  .visually-hidden {
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
</style>
