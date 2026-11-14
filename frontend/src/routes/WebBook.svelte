<script lang="ts">
  import { onMount } from "svelte";
  import { getApi } from "../lib/api/client";
  import type { WebBook } from "../lib/api/client";
  import { getRouter } from "../lib/ctx";
  import { linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import { pageSrc } from "../lib/reader/pages";
  import { getWebPage } from "../lib/reader/webProgress";
  import { createSearch } from "../lib/stores/search.svelte";
  import { placement } from "../lib/stores/placement.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { rejectTag } from "../lib/item/reject";
  import { saveWebItem, saveStateFor, savedHrefFor } from "../lib/web/saveFlow";
  import { gatedSrc } from "../lib/webImageQueue";
  import Icon from "../lib/components/Icon.svelte";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const search = createSearch(api);

  const source = $derived(match.params.source);
  const id = $derived(match.params.id);
  const key = $derived(source + ":" + id);

  let book = $state<WebBook | null>(null);
  let status = $state<"loading" | "ready" | "error">("loading");
  let banOpen = $state(false);
  let last = $state<number | null>(null);

  async function load() {
    status = "loading";
    try {
      if (source !== "nhentai") throw new Error("unsupported source");
      book = await api.webBook(source, id);
      last = getWebPage(key);
      status = "ready";
    } catch {
      status = "error";
    }
  }
  onMount(() => void load());

  const item = $derived(book?.item ?? null);
  const saveState = $derived(item ? saveStateFor(item, search.saveStateOf(item)) : "idle");
  const savedHref = $derived(item ? savedHrefFor(item, search.saveStateOf(item)) : undefined);
  const count = $derived(book?.page_count ?? 0);
  const pages = $derived(Array.from({ length: count }, (_, i) => i + 1));
  const readBase = $derived("/read/web/" + encodeURIComponent(source) + "/" + encodeURIComponent(id));
  const heroChips = $derived.by(() => {
    if (!book) return [];
    const tags = Object.values(book.tags ?? {}).flat().slice(0, 2);
    return [book.language, book.event, book.translator, ...tags].filter((c): c is string => !!c);
  });
  const by = $derived([book?.circle, book?.artist].filter(Boolean).join(" · "));
  const groups = $derived(Object.entries(book?.tags ?? {}).filter(([, v]) => v.length > 0));
  const allTags = $derived(groups.flatMap(([, v]) => v));

  function back() {
    if (router.canGoBack()) history.back();
    else router.navigate("/");
  }
  function save() {
    if (!item) return;
    void saveWebItem(
      { ask: (i) => placement.ask(i), save: (i, p) => search.save(i, p), toast: (t) => toasts.push(t) },
      item,
    );
  }
  function reject(tag: string) {
    banOpen = false;
    void rejectTag(api, toasts, tag);
  }
</script>

<div class="page">
  {#if item}
    <div class="backdrop" style:background-image={`url("${item.thumb_url}")`} aria-hidden="true"></div>
  {/if}
  <header class="bar">
    <button class="ib" type="button" aria-label="Back" onclick={back}><Icon name="arrow-left" size={20} /></button>
  </header>

  {#if status === "loading"}
    <p class="note" role="status">Loading…</p>
  {:else if status === "error" || !book || !item}
    <div class="note">
      <p>Could not load this book.</p>
      <button class="btn" type="button" onclick={load}><Icon name="refresh" size={18} /> Retry</button>
    </div>
  {:else}
    <div class="cols">
      <main class="main">
        <section class="hero">
          <img class="cover" src={item.thumb_url} alt="" />
          <div class="info">
            {#if heroChips.length}
              <ul class="chips">{#each heroChips as c (c)}<li>{c}</li>{/each}</ul>
            {/if}
            {#if book.title_sub}<p class="sub">{book.title_sub}</p>{/if}
            <h1 class="title">{book.title_main}</h1>
            {#if by}<p class="by">by {by}</p>{/if}
            <div class="actions">
              {#if count > 0}
                <button class="btn primary" type="button" onclick={() => router.navigate(readBase)}>
                  <Icon name="book" size={20} />{last ? "Continue" : "Read"}
                </button>
              {/if}
              {#if saveState === "in_library" && savedHref}
                <a class="ib sq" href={savedHref} aria-label="In library" title="In library" onclick={(e) => linkClick(e, router)}><Icon name="check" size={20} /></a>
              {:else}
                <button
                  class="ib sq"
                  type="button"
                  aria-label={saveState === "queued" ? "Saving" : saveState === "blocked" ? "Blocked by a rule" : "Save"}
                  title="Save"
                  disabled={saveState !== "idle" || item.saveable === false}
                  onclick={save}
                >
                  <Icon name={saveState === "queued" ? "loader" : saveState === "blocked" ? "alert" : "download"} size={20} />
                </button>
              {/if}
              <a class="ib sq" href={"https://nhentai.net/g/" + encodeURIComponent(id) + "/"} target="_blank" rel="noopener noreferrer" aria-label="Open on nhentai" title="Open on nhentai"><Icon name="external-link" size={20} /></a>
              {#if allTags.length}
                <button class="ib sq" type="button" aria-label="Reject a tag" title="Reject a tag" aria-expanded={banOpen} onclick={() => (banOpen = !banOpen)}><Icon name="ban" size={20} /></button>
              {/if}
            </div>
            {#if banOpen}
              <div class="ban" role="group" aria-label="Reject a tag">
                {#each allTags as t (t)}
                  <button type="button" class="chip" onclick={() => reject(t)}>{t}</button>
                {/each}
              </div>
            {/if}
          </div>
        </section>

        {#if count > 0}
          <ul class="grid">
            {#each pages as n (n)}
              <li>
                <a
                  class="thumb"
                  class:last={last === n}
                  href={readBase + "?p=" + n}
                  aria-label={"Page " + n}
                  onclick={(e) => linkClick(e, router)}
                >
                  <img alt="" use:gatedSrc={{ src: pageSrc(book.page_thumb_url, n), prio: n <= 6 ? "focus" : "prefetch" }} />
                </a>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="note">This book has no pages.</p>
        {/if}
      </main>

      {#if groups.length}
        <aside class="side">
          {#each groups as [type, names] (type)}
            <section>
              <h2>{type}</h2>
              <ul class="chips">{#each names as n (n)}<li>{n}</li>{/each}</ul>
            </section>
          {/each}
        </aside>
      {/if}
    </div>
  {/if}
</div>

<style>
  .page { position: relative; min-height: 100%; padding: 0 var(--s-4) var(--s-6); max-width: var(--content-max); margin: 0 auto; }
  .backdrop { position: absolute; inset: 0 0 auto 0; height: 420px; background-size: cover; background-position: center; filter: blur(40px); opacity: .35; mask-image: linear-gradient(#000, transparent); -webkit-mask-image: linear-gradient(#000, transparent); pointer-events: none; z-index: 0; }
  .bar, .cols, .note { position: relative; z-index: 1; }
  .bar { display: flex; padding: var(--s-2) 0; }
  .ib { min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line-strong); border-radius: var(--r-md); background: rgb(20 20 24 / .6); color: var(--text); cursor: pointer; text-decoration: none; font: inherit; }
  .ib:disabled { opacity: .5; cursor: default; }
  .btn { min-height: 44px; display: inline-flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-4); border: 1px solid var(--line-strong); border-radius: var(--r-md); background: transparent; color: var(--text); font: inherit; cursor: pointer; }
  .btn.primary { background: #fff; color: #111; border-color: #fff; font-weight: 600; }
  .ib:focus-visible, .btn:focus-visible, .thumb:focus-visible, .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .cols { display: grid; grid-template-columns: 1fr; gap: var(--s-5); }
  .hero { display: flex; flex-direction: column; align-items: center; gap: var(--s-4); text-align: center; }
  .cover { width: 200px; max-width: 60%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: var(--r-md); background: var(--surface); }
  .info { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); min-width: 0; }
  .title { margin: 0; font-size: var(--t-20); line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .sub, .by { margin: 0; color: var(--muted); font-size: var(--t-13); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-1); list-style: none; margin: 0; padding: 0; justify-content: inherit; }
  .chips li, .chip { padding: 2px var(--s-2); border-radius: 999px; background: var(--surface); color: var(--text); font-size: var(--t-12); border: 0; }
  .chip { min-height: 44px; padding: 0 var(--s-3); cursor: pointer; font: inherit; font-size: var(--t-13); }
  .actions { display: flex; gap: var(--s-2); flex-wrap: wrap; justify-content: center; margin-top: var(--s-2); }
  .ban { display: flex; flex-wrap: wrap; gap: var(--s-1); justify-content: center; }
  .grid { list-style: none; margin: var(--s-5) 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: var(--s-2); }
  .thumb { display: block; aspect-ratio: 2 / 3; background: var(--surface); border-radius: var(--r-sm); overflow: hidden; border: 2px solid transparent; }
  .thumb.last { border-color: var(--progress); }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .side h2 { margin: 0 0 var(--s-1); font-size: var(--t-12); text-transform: uppercase; color: var(--muted); letter-spacing: .04em; }
  .side section { margin-bottom: var(--s-4); }
  .note { text-align: center; color: var(--muted); padding: var(--s-5) 0; }
  @media (min-width: 900px) {
    .cols { grid-template-columns: 1fr 260px; align-items: start; }
    .hero { flex-direction: row; align-items: flex-start; text-align: left; }
    .cover { max-width: none; flex: none; }
    .info { align-items: flex-start; }
    .actions, .ban { justify-content: flex-start; }
  }
</style>
