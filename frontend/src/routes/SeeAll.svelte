<script lang="ts">
  import { untrack, tick } from "svelte";
  import { getApi } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import type { Kind, WebItem } from "../lib/api/client";
  import { ApiError as ApiErrorClass } from "../lib/api/client";
  import { seeAllGrid } from "../lib/stores/shared.svelte";
  import Icon from "../lib/components/Icon.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { onMount } from "svelte";
  import { SvelteURLSearchParams } from "svelte/reactivity";
  import { viewSettings } from "../lib/stores/viewSettings.svelte";
  import { pageOf, remapPage } from "../lib/browse/pager";
  import type { Mode } from "../lib/browse/layout";
  import ResultsGrid from "../lib/browse/ResultsGrid.svelte";
  import Pager from "../lib/browse/Pager.svelte";
  import ViewBar from "../lib/browse/ViewBar.svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();

  let h1: HTMLHeadingElement | undefined;
  let notice = $state<string | null>(null);

  onMount(() => {
    h1?.focus();
    viewSettings.load(api);
  });

  const source = $derived.by(() => {
    switch (match.name) {
      case "library_images": return "stash_images";
      case "library_videos": return "stash_videos";
      case "library_series": return "komga_series";
      case "library_books": return "komga_books";
      default: return match.query.get("source") ?? "";
    }
  });

  const q = $derived(match.query.get("q") ?? "");
  const sort = $derived(match.query.get("sort") ?? "");
  const favorite = $derived(match.query.get("favorite") === "true");
  const seed = $derived(match.query.get("seed") ?? undefined);
  const page = $derived(pageOf(match.query.get("page")));
  const vs = $derived(viewSettings.get(source));
  let pagerEl = $state<HTMLSelectElement | HTMLInputElement | null>(null);

  function sourceToKind(s: string): Kind | null {
    if (s === "stash_images") return "images";
    if (s === "stash_videos") return "videos";
    if (s === "komga_series") return "series";
    if (s === "komga_books") return "books";
    return null;
  }

  const kind = $derived(sourceToKind(source));
  const isLibrary = $derived(kind !== null);

  const title = $derived.by(() => {
    switch (source) {
      case "stash_images": return "Images";
      case "stash_videos": return "Videos";
      case "komga_series": return "Series";
      case "komga_books": return "Books";
      default: return source || "Results";
    }
  });

  const grid = seeAllGrid;

  const listKey = $derived(
    [source, q, sort, favorite ? "1" : "0", seed ?? "", String(vs.per_page)].join("|"),
  );

  $effect(() => {
    if (!viewSettings.ready) return;
    const k = sourceToKind(source);
    const src = source;
    const qq = q;
    const srt = sort;
    const fav = favorite;
    const sd = seed;
    const pp = vs.per_page;
    const adopt = untrack(() => grid.listKey === listKey && grid.status === "done" && grid.takeCrossed()); const pg = adopt ? untrack(() => grid.page) : page;

    if (k) {
      const loader = async (p: number, signal: AbortSignal) => {
        const r = await api.list(
          k,
          {
            page: p,
            page_size: pp,
            q: qq || undefined,
            sort: (srt || undefined) as "newest" | "rating" | "random" | undefined,
            favorite: fav ? true : undefined,
            seed: srt === "random" && sd && Number.isFinite(Number(sd)) ? Number(sd) : undefined,
          },
          signal,
        );
        notice = r.notice?.message ?? null;
        return { items: r.items, total: r.total ?? null, next_page: r.next_page ?? null, page: r.page ?? null, pages: r.pages ?? null, page_size: r.page_size ?? null, stats: r.stats ?? null };
      };
      untrack(() => grid.open(listKey, loader, pg));
    } else {
      notice = null;
      const loader = async (p: number, signal: AbortSignal) => {
        const r = await api.search({ q: qq, sources: [src], page: p, page_size: pp }, signal);
        const s = r.sections?.find((x: { id: string }) => x.id === src);
        return {
          items: s?.items ?? [],
          total: s?.total ?? null,
          next_page: s?.next_page ?? null,
          pages: s?.pages ?? null,
          page_size: s?.page_size ?? null,
          stats: s?.stats ?? null,
          hidden: s?.hidden ?? null,
        };
      };
      untrack(() => grid.open(listKey, loader, pg));
    }
  });

  // Sync URL page param to served page
  $effect(() => {
    if (grid.status !== "done") return;
    const gp = grid.page;
    if (typeof gp !== "number" || gp < 1) return;
    if (gp === page) return;
    const qs = new SvelteURLSearchParams(match.query);
    if (gp === 1) qs.delete("page");
    else qs.set("page", String(gp));
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
  });

  // Scroll to top and focus pager after a page finishes loading
  let lastFocusedKey = "";
  $effect(() => {
    const status = grid.status;
    const gp = grid.page;
    if (status !== "done") return;
    const pg = untrack(() => page);
    if (gp !== pg) return;
    const key = untrack(() => listKey) + "|" + String(gp);
    if (lastFocusedKey === key) return;
    lastFocusedKey = key;
    untrack(() => {
      if (grid.scrollY > 0) return;
      window.scrollTo(0, 0);
      (async () => {
        await tick();
        pagerEl?.focus();
      })();
    });
  });

  // --- save state for web items ---
  let saveStates = $state<Record<string, "queued" | "in_library">>({});

  async function handleSave(item: WebItem) {
    const key = item.source + ":" + item.post_id;
    saveStates[key] = "queued";
    try {
      await api.save({ source: item.source, post_id: item.post_id });
      toasts.push({ kind: "info", message: "Added to queue", actionLabel: "View", href: "/queue" });
    } catch (e) {
      if (e instanceof ApiErrorClass && e.status === 409) {
        saveStates[key] = "in_library";
      } else {
        delete saveStates[key];
        toasts.push({ kind: "error", message: "Could not save. Try again." });
      }
    }
  }

  // --- URL query updates ---
  function setPage(p: number) {
    const qs = new SvelteURLSearchParams(match.query);
    if (p === 1) qs.delete("page");
    else qs.set("page", String(p));
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""));
  }

  function onSortChange(value: string) {
    const qs = new SvelteURLSearchParams(match.query);
    qs.delete("page");
    if (value) {
      qs.set("sort", value);
      if (value === "random") {
        qs.set("seed", String(Math.floor(Math.random() * 1e8)));
      } else {
        qs.delete("seed");
      }
    } else {
      qs.delete("sort");
      qs.delete("seed");
    }
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
  }

  function onFavToggle() {
    const qs = new SvelteURLSearchParams(match.query);
    qs.delete("page");
    if (favorite) qs.delete("favorite");
    else qs.set("favorite", "true");
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
  }

  async function onPerPage(n: number) {
    const first = (grid.page - 1) * vs.per_page + 1;
    if (!Number.isInteger(n) || n < 1 || n > vs.per_page_max) return;
    // URL and store change in the same tick so the grid effect sees the new pair once
    const qs = new SvelteURLSearchParams(match.query);
    const pg = remapPage(first, n);
    if (pg === 1) qs.delete("page");
    else qs.set("page", String(pg));
    const search = qs.toString();
    router.navigate(match.path + (search ? `?${search}` : ""), { replace: true });
    await viewSettings.set(source, { per_page: n });
  }

  function onMode(m: Mode) {
    viewSettings.set(source, { mode: m });
  }

  function onZoom(z: number) {
    viewSettings.set(source, { zoom: z });
  }

  function onZoomPreview(z: number) {
    viewSettings.preview(source, { zoom: z });
  }

  function onKey(e: KeyboardEvent) {
    const t = e.target as HTMLElement | null;
    if (t) {
      const tag = t.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (t.isContentEditable) return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    if (e.key === "ArrowLeft") {
      const gp = grid.page;
      if (gp > 1) setPage(gp - 1);
    } else if (e.key === "ArrowRight") {
      const gp = grid.page;
      const hasNext = grid.pages !== null ? gp < grid.pages : grid.hasNext;
      if (hasNext) setPage(gp + 1);
    }
  }

  function onNav(e: MouseEvent) {
    linkClick(e, router);
  }

</script>

<svelte:window onkeydown={onKey} />

<div class="content">
  <h1 class="sr-only" tabindex="-1" bind:this={h1}>{title}</h1>

  <header class="sticky-header">
    <div class="header-row">
      <button class="back-btn" aria-label="Back" onclick={() => history.back()}>
        <Icon name="arrow-left" size={20} />
      </button>
      <h2 class="header-title">{title} ({grid.total ?? "…"})</h2>
    </div>

    {#if q}
      <div class="q-chips">
        <span class="q-chip">{q}</span>
      </div>
    {/if}

    {#if isLibrary}
      <div class="controls">
        <select aria-label="Sort" class="sort-select" value={sort} onchange={(e) => onSortChange((e.target as HTMLSelectElement).value)}>
          <option value="">Newest</option>
          <option value="rating">Rating</option>
          <option value="random">Random</option>
        </select>
        <button
          class="fav-toggle"
          aria-pressed={favorite}
          onclick={onFavToggle}
        >
          <Icon name={favorite ? "heart-filled" : "heart"} size={16} />
          Favorites
        </button>
      </div>
    {/if}
    {#if viewSettings.ready}
    <ViewBar modes={vs.modes as Mode[]} mode={vs.mode as Mode} perPage={vs.per_page} zoom={vs.zoom} options={vs.per_page_options} max={vs.per_page_max} onmode={onMode} onperpage={onPerPage} onzoom={onZoom} onzoompreview={onZoomPreview} />
    {/if}
  </header>

  {#if notice}<p class="notice" role="status">{notice}</p>{/if}

  {#if viewSettings.ready}
  {#if grid.status !== "error" && grid.status !== "idle"}
    <Pager page={grid.page} pages={grid.pages} hasNext={grid.hasNext} perPage={vs.per_page} shown={grid.items.length} total={grid.total} stats={grid.stats ? { megapixels: grid.stats.megapixels ?? null, size_bytes: grid.stats.size_bytes ?? null } : null} onpage={setPage} bind:selectEl={pagerEl} />
  {/if}

  {#if grid.status === "loading" || grid.status === "idle"}
    <ResultsGrid items={[]} mode={vs.mode as Mode} zoom={vs.zoom} loading={true} skeletons={vs.per_page} saveStates={saveStates} onsave={handleSave} onnavigate={onNav} />
  {:else if grid.status === "error"}
    <div class="error-box">
      <p>Could not load this list.</p>
      <button class="retry-btn" onclick={() => grid.retry()}>Retry</button>
    </div>
  {:else if grid.items.length === 0}
    <div class="empty">Nothing here.</div>
  {:else}
    <ResultsGrid items={grid.items} mode={vs.mode as Mode} zoom={vs.zoom} loading={false} skeletons={vs.per_page} saveStates={saveStates} onsave={handleSave} onnavigate={onNav} />
  {/if}

  {#if grid.status !== "error" && grid.status !== "idle"}
    <Pager page={grid.page} pages={grid.pages} hasNext={grid.hasNext} perPage={vs.per_page} shown={grid.items.length} total={grid.total} stats={grid.stats ? { megapixels: grid.stats.megapixels ?? null, size_bytes: grid.stats.size_bytes ?? null } : null} onpage={setPage} />
  {/if}
  {/if}
</div>

<style>
  .content { max-width: var(--content-max); margin: 0 auto; padding: 0 var(--s-4); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
  .sticky-header { position: sticky; top: 0; background: var(--surface); z-index: 10; padding: var(--s-4) 0; }
  .header-row { display: flex; align-items: center; gap: var(--s-4); padding-right: var(--sfw-inset); }
  .back-btn { min-width: 44px; min-height: 44px; display: grid; place-items: center; border: none; background: none; cursor: pointer; color: var(--text); }
  .header-title { font-size: 1.25rem; font-weight: 700; margin: 0; color: var(--text); }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-4); margin-top: var(--s-4); }
  .sort-select { padding: var(--s-2) var(--s-4); border: 1px solid var(--text); border-radius: var(--s-2); background: var(--surface); color: var(--text); }
  .fav-toggle { min-height: 44px; display: flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-4); border: 1px solid var(--text); border-radius: var(--s-2); background: none; color: var(--text); cursor: pointer; }
  .error-box { padding: var(--s-4); text-align: center; color: var(--text); }
  .retry-btn { margin-top: var(--s-4); padding: var(--s-2) var(--s-4); border: none; border-radius: var(--s-2); background: var(--text); color: var(--surface); cursor: pointer; }
  .empty { text-align: center; padding: var(--s-8); color: var(--text); }
  .notice { margin: 0; font-size: 0.875rem; color: var(--muted); }
</style>
