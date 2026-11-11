<script lang="ts">
  import { type Match } from "../lib/router";
  import { getRouter } from "../lib/ctx";
  import {
    SECTIONS,
    searchSections,
    isSectionId,
    type SectionId,
    type Section,
    type Group,
  } from "../lib/options/sections";
  import Icon from "../lib/components/Icon.svelte";
  import { SvelteMap } from "svelte/reactivity";
  import Rules from "./Rules.svelte";
  import ImageViewerCard from "../lib/options/ImageViewerCard.svelte";

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

  $effect(() => {
    if (!activeSectionId) return;
    h1El?.focus();
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
    router.navigate(`/options/${id}`);
  }

  function backToOptions() {
    router.navigate("/options");
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
</script>

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
          {#if activeSectionId === "viewing" && card.title === "Image viewer"}
            <ImageViewerCard />
          {:else}
            <section class="card">
              <h2 class="card-title">{card.title}</h2>
              <dl>
                {#each card.rows as row (row.label)}
                  <div class="row">
                    <dt>{row.label}</dt>
                    <dd>{row.hint}</dd>
                  </div>
                {/each}
              </dl>
            </section>
          {/if}
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
            {#each hit.cards as card (card.title)}
              <section class="card">
                <h3 class="card-title">{card.title}</h3>
                <dl>
                  {#each card.rows as row (row.label)}
                    <div class="row">
                      <dt>{row.label}</dt>
                      <dd>{row.hint}</dd>
                    </div>
                  {/each}
                </dl>
              </section>
            {/each}
          {/each}
        {/if}
      {:else}
        <!-- Normal section view -->
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
            {#if activeSectionId === "viewing" && card.title === "Image viewer"}
              <ImageViewerCard />
            {:else}
              <section class="card">
                <h2 class="card-title">{card.title}</h2>
                <dl>
                  {#each card.rows as row (row.label)}
                    <div class="row">
                      <dt>{row.label}</dt>
                      <dd>{row.hint}</dd>
                    </div>
                  {/each}
                </dl>
              </section>
            {/if}
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
    color: var(--text-primary, #1a1a1a);
  }

  /* ── Desktop two-pane ─────────────────────────────────── */
  .desktop {
    flex-direction: row;
  }

  .sidebar {
    width: 280px;
    min-width: 280px;
    border-right: 1px solid var(--border, #e0e0e0);
    overflow-y: auto;
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .pane {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px;
  }

  .pane-title {
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0 0 20px;
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
    border: 1px solid var(--border, #e0e0e0);
    border-radius: var(--radius-md, 8px);
    padding: 0 10px;
    min-height: 44px;
    background: var(--surface, #fff);
  }

  .search-wrap input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 0.9rem;
    min-height: 44px;
    background: transparent;
    color: var(--text-primary, #1a1a1a);
  }

  .search-wrap input::placeholder {
    color: var(--text-muted, #999);
  }

  .clear-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    min-width: 28px;
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-secondary, #666);
    border-radius: 50%;
  }

  .clear-btn:hover {
    color: var(--text-primary, #1a1a1a);
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
    color: var(--text-muted, #999);
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
    border-radius: var(--radius-md, 8px);
    background: none;
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--text-primary, #1a1a1a);
    text-align: left;
    transition: background 120ms;
  }

  .section-row:hover {
    background: var(--surface-hover, #f5f5f5);
  }

  .section-row:focus-visible {
    outline: 2px solid var(--accent, #4f8ef7);
    outline-offset: -2px;
  }

  .section-row.active {
    background: var(--accent-subtle, #e8f0fe);
    font-weight: 600;
  }

  .section-row.later {
    opacity: 0.55;
  }

  .section-row-label {
    flex: 1;
  }

  .later-tag {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted, #999);
    border: 1px solid var(--border, #e0e0e0);
    border-radius: 4px;
    padding: 1px 5px;
  }

  .count-badge {
    font-size: 0.75rem;
    color: var(--text-secondary, #666);
    min-width: 20px;
    text-align: center;
  }

  /* ── Cards ────────────────────────────────────────────── */
  .card {
    border: 1px solid var(--border, #e0e0e0);
    border-radius: var(--radius-md, 8px);
    padding: 16px 20px;
    margin-bottom: 16px;
  }

  .card-title {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 12px;
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: 44px;
    padding: 6px 0;
  }

  .row dt {
    font-weight: 500;
  }

  .row dd {
    margin: 0;
    color: var(--text-secondary, #666);
    font-size: 0.85rem;
  }

  .coming-later {
    color: var(--text-muted, #999);
    font-style: italic;
  }

  /* ── Search results in pane ───────────────────────────── */
  .result-heading {
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-secondary, #666);
    margin: 20px 0 8px;
  }

  /* ── No results ───────────────────────────────────────── */
  .no-results {
    color: var(--text-muted, #999);
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
    color: var(--text-primary, #1a1a1a);
    border-radius: 50%;
  }

  .back-btn:hover {
    background: var(--surface-hover, #f5f5f5);
  }

  .back-btn:focus-visible {
    outline: 2px solid var(--accent, #4f8ef7);
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
