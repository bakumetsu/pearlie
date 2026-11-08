<script lang="ts">
  import type { Pill, SiteId } from "../query";

  let {
    pill,
    sites,
    unavailable = [],
    onpill,
    onsites,
  }: {
    pill: Pill;
    sites: SiteId[];
    unavailable?: SiteId[];
    onpill: (p: Pill) => void;
    onsites: (s: SiteId[]) => void;
  } = $props();

  const PILLS: { id: Pill; label: string }[] = [
    { id: "all", label: "All" },
    { id: "images", label: "Images" },
    { id: "videos", label: "Videos" },
    { id: "books", label: "Books" },
    { id: "web", label: "Web" },
  ];

  const SITE_ORDER: { id: SiteId; label: string }[] = [
    { id: "danbooru", label: "Danbooru" },
    { id: "gelbooru", label: "Gelbooru" },
    { id: "rule34", label: "Rule34" },
    { id: "nhentai", label: "nhentai" },
  ];

  function toggleSite(id: SiteId): void {
    if (unavailable.includes(id)) return;
    const next = sites.includes(id) ? sites.filter((s) => s !== id) : [...sites, id];
    const ordered = SITE_ORDER.map((d) => d.id).filter((id) => next.includes(id));
    onsites(ordered);
  }

  const showSites = pill === "all" || pill === "web";
</script>

<div class="pillbar">
  <div class="pills" role="group" aria-label="Search scope">
    {#each PILLS as p (p.id)}
      <button
        class="pill-btn"
        type="button"
        aria-pressed={pill === p.id}
        onclick={() => onpill(p.id)}
      >
        <span class="pill-visual" class:active={pill === p.id}>{p.label}</span>
      </button>
    {/each}
  </div>

  {#if showSites}
    <div class="sites" role="group" aria-label="Sites">
      {#each SITE_ORDER as s (s.id)}
        {@const disabled = unavailable.includes(s.id)}
        <button
          class="site-btn"
          type="button"
          aria-pressed={sites.includes(s.id)}
          disabled={disabled}
          onclick={() => toggleSite(s.id)}
        >
          <span class="site-visual" class:active={sites.includes(s.id)}>
            {disabled ? `${s.label} · not configured` : s.label}
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .pillbar {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }

  .pills {
    display: flex;
    gap: var(--s-1);
  }

  .pill-btn {
    display: grid;
    place-items: center;
    min-height: 44px;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    border-radius: var(--r-md);
  }

  .pill-visual {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 36px;
    padding: 0 var(--s-3);
    border-radius: var(--r-md);
    font-size: var(--t-13);
    color: var(--muted);
    background: var(--surface);
    border: 1px solid var(--line);
    transition: background 0.12s, color 0.12s, border-color 0.12s;
  }

  .pill-visual.active {
    background: var(--accent-bg);
    color: var(--accent);
    border-color: var(--accent);
  }

  .sites {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-1);
  }

  .site-btn {
    display: grid;
    place-items: center;
    min-height: 44px;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    border-radius: var(--r-md);
  }

  .site-btn:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .site-visual {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 var(--s-2);
    border-radius: var(--r-sm);
    font-size: var(--t-12);
    color: var(--muted);
    background: var(--surface);
    border: 1px solid var(--line);
  }

  .site-visual.active {
    background: var(--accent-bg);
    color: var(--accent);
    border-color: var(--accent);
  }
</style>
