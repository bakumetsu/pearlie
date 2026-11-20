<script lang="ts">
  import { untrack } from "svelte";
  import { getApi, ApiError } from "../api/client";
  import type { RecommendItem } from "../api/client";
  import Icon from "../components/Icon.svelte";

  let { source, id, kind = "book", recLimit = 6, randomLimit = 5, onopen }: {
    source: string;
    id: string;
    kind?: "book" | "series";
    recLimit?: number;
    randomLimit?: number;
    onopen: (item: RecommendItem) => void;
  } = $props();

  const api = getApi();

  type Phase = "loading" | "ready" | "error";
  type Section = { phase: Phase; items: RecommendItem[]; rateLimited: boolean; wait: number };
  const fresh = (): Section => ({ phase: "loading", items: [], rateLimited: false, wait: 0 });

  let rec = $state<Section>(fresh());
  let rnd = $state<Section>(fresh());

  // The panel never blocks the page, and a stale answer never overwrites a newer one.
  let recToken = 0;
  let rndToken = 0;
  let timers: ReturnType<typeof setInterval>[] = [];

  function countdown(s: Section, seconds: number): void {
    s.wait = Math.ceil(seconds);
    const t = setInterval(() => {
      s.wait = Math.max(0, s.wait - 1);
      if (s.wait === 0) {
        clearInterval(t);
        timers = timers.filter((x) => x !== t);
      }
    }, 1000);
    timers.push(t);
  }

  function fail(s: Section, e: unknown): void {
    s.phase = "error";
    s.items = [];
    s.rateLimited = e instanceof ApiError && e.code === "rate_limited";
    if (s.rateLimited) countdown(s, (e as ApiError).retryAfter ?? 0);
  }

  async function loadRec(): Promise<void> {
    const token = ++recToken;
    rec = fresh();
    try {
      const r = await api.recommend({ source, id, kind, limit: recLimit });
      if (token !== recToken) return;
      rec.items = r.items;
      rec.phase = "ready";
    } catch (e) {
      if (token === recToken) fail(rec, e);
    }
  }

  async function loadRandom(): Promise<void> {
    const token = ++rndToken;
    rnd = fresh();
    try {
      const r = await api.recommendRandom({ source, limit: randomLimit, exclude: id });
      if (token !== rndToken) return;
      rnd.items = r.items;
      rnd.phase = "ready";
    } catch (e) {
      if (token === rndToken) fail(rnd, e);
    }
  }

  $effect(() => {
    void source;
    void id;
    void kind;
    untrack(() => {
      void loadRec();
      void loadRandom();
    });
    return () => {
      recToken++;
      rndToken++;
      for (const t of timers) clearInterval(t);
      timers = [];
    };
  });
</script>

{#snippet rows(items: RecommendItem[])}
  <div class="mlt">
    {#each items as it (it.source + ":" + it.id)}
      <button class="mrow" type="button" onclick={() => onopen(it)}>
        {#if it.thumb_url}<img class="mth" src={it.thumb_url} alt="" loading="lazy" />{:else}<span class="mth"></span>{/if}
        <span class="mtx">
          <span class="mtt">{it.title}</span>
          {#if it.author}<span class="why">{it.author}</span>{/if}
        </span>
        {#if it.saved}<span class="tick" role="img" aria-label="In library"><Icon name="check" size={16} /></span>{/if}
      </button>
    {/each}
  </div>
{/snippet}

{#snippet body(s: Section, empty: string, failText: string, retry: () => void)}
  {#if s.phase === "loading"}
    <div class="mlt" aria-busy="true"><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>
  {:else if s.phase === "error"}
    <div class="state" role="alert">
      {s.rateLimited ? "Try again in a moment." : failText}
      <button class="ib" type="button" disabled={s.wait > 0} onclick={retry}><Icon name="refresh" size={18} />Retry{s.wait > 0 ? " (" + s.wait + "s)" : ""}</button>
    </div>
  {:else if s.items.length === 0}
    <div class="state">{empty}</div>
  {:else}
    {@render rows(s.items)}
  {/if}
{/snippet}

<section aria-label="Recommendations">
  <h3>Recommendations<em>{source === "nhentai" ? "nhentai only" : "Stump only"}</em></h3>
  {@render body(rec, "Nothing similar found.", "Could not load.", loadRec)}
</section>
<section aria-label="Random">
  <h3 class="hrow">
    Random
    <button class="ib" type="button" aria-label="Shuffle" title="Shuffle" disabled={rnd.phase === "loading" || rnd.wait > 0} onclick={loadRandom}><Icon name="refresh" size={20} /></button>
  </h3>
  {@render body(rnd, "Nothing to show.", "Could not load.", loadRandom)}
</section>

<style>
  section { display: flex; flex-direction: column; gap: var(--s-1); min-width: 0; }
  h3 { margin: 0; font-size: var(--t-12); color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 500; }
  h3 em { font-style: normal; text-transform: none; letter-spacing: 0; margin-left: 6px; }
  .hrow { display: flex; align-items: center; justify-content: space-between; }
  .ib { min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: var(--s-2); border: 1px solid var(--line-strong); border-radius: var(--r-md); background: transparent; color: var(--text); font: inherit; cursor: pointer; }
  .hrow .ib { border-color: transparent; }
  .ib:disabled { opacity: .5; cursor: default; }
  .ib:focus-visible, .mrow:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .mlt { display: flex; flex-direction: column; gap: 4px; }
  .mrow { position: relative; display: grid; grid-template-columns: 48px 1fr; gap: var(--s-3); align-items: center; min-height: 72px; padding: 4px; border: 0; border-radius: 8px; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .mrow:hover { background: var(--surface); }
  .mth { width: 48px; aspect-ratio: 2 / 3; border-radius: 4px; object-fit: cover; background: var(--surface); display: block; }
  .mtx { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .mtt { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: var(--t-13); }
  .why { font-size: var(--t-12); color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tick { position: absolute; top: 6px; left: 6px; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; background: var(--progress); color: #111; }
  .skel { height: 72px; border-radius: 8px; background: linear-gradient(90deg, var(--surface), #26262c, var(--surface)); background-size: 200% 100%; animation: sh 1.2s linear infinite; }
  @keyframes sh { to { background-position: -200% 0; } }
  @media (prefers-reduced-motion: reduce) { .skel { animation: none; } }
  .state { padding: var(--s-4) 0; color: var(--muted); font-size: var(--t-13); display: flex; flex-direction: column; gap: var(--s-2); align-items: flex-start; }
  .state .ib { padding: 0 var(--s-3); }
</style>
