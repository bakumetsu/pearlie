<script lang="ts">
  import { untrack } from "svelte";
  import { getApi } from "../lib/api/client";
  import { ApiError } from "../lib/api/client";
  import type { WebBook } from "../lib/api/client";
  import { getRouter, findJobs } from "../lib/ctx";
  import { linkClick } from "../lib/router";
  import type { Match } from "../lib/router";
  import { getWebPage } from "../lib/reader/webProgress";
  import { createSearch } from "../lib/stores/search.svelte";
  import { placement } from "../lib/stores/placement.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import { rejectTag } from "../lib/item/reject";
  import type { ToastsLike } from "../lib/item/itemView.svelte";
  import { saveWebItem, saveStateFor, savedHrefFor } from "../lib/web/saveFlow";
  import { restoreSaved } from "../lib/web/restoreSaved";
  import Icon from "../lib/components/Icon.svelte";
  import BookPage from "../lib/book/BookPage.svelte";
  import PageGrid from "../lib/book/PageGrid.svelte";
  import TagChips from "../lib/item/TagChips.svelte";
  import SidePanel from "../lib/item/SidePanel.svelte";
  import { tagSearchHref } from "../lib/query";

  let { match }: { match: Match } = $props();

  const api = getApi();
  const router = getRouter();
  const search = createSearch(api);
  const jobsStore = findJobs();
  $effect(() => {
    if (jobsStore) search.settle(jobsStore.items);
  });

  const source = $derived(match.params.source);
  const id = $derived(match.params.id);
  const key = $derived(source + ":" + id);

  let book = $state<WebBook | null>(null);
  let status = $state<"loading" | "ready" | "error">("loading");
  let rejected = $state<string[]>([]);
  let last = $state<number | null>(null);
  let errorText = $state("Could not load this book.");

  let loadToken = 0;
  async function load() {
    const token = ++loadToken;
    status = "loading";
    errorText = "Could not load this book.";
    try {
      if (source !== "nhentai") throw new Error("unsupported source");
      const b = await api.webBook(source, id);
      if (token !== loadToken) return;
      book = b;
      last = getWebPage(key);
      status = "ready";
    } catch (e) {
      if (token !== loadToken) return;
      if (e instanceof ApiError && e.message) errorText = e.message;
      status = "error";
    }
  }
  $effect(() => {
    void key;
    untrack(() => void load());
  });

  const item = $derived(book?.item ?? null);
  const saveState = $derived(item ? saveStateFor(item, search.saveStateOf(item)) : "idle");
  const savedHref = $derived(item ? savedHrefFor(item, search.saveStateOf(item)) : undefined);
  const count = $derived(book?.page_count ?? 0);
  const readBase = $derived("/read/web/" + encodeURIComponent(source) + "/" + encodeURIComponent(id));
  // Name block: `name_lines` from the backend (Latin first, kana last); old fallback: big romaji (`title`), the Japanese title as stored, English (title_main when it differs)
  const names = $derived.by(() => {
    if (!book) return { big: "", sub: [] as string[] };
    const lines = (book.name_lines ?? []).map((l) => l.trim()).filter(Boolean);
    if (lines.length > 0) return { big: lines[0], sub: lines.slice(1) };
    const big = (book.title || book.title_main).trim();
    const sub = [book.title_sub?.trim() ?? "", book.title_main.trim()].filter((l, i, a) => l && l !== big && a.indexOf(l) === i);
    return { big, sub };
  });
  const groups = $derived(Object.entries(book?.tags ?? {}).filter(([, v]) => v.length > 0));

  function back() {
    if (router.canGoBack()) history.back();
    else router.navigate("/");
  }
  function save() {
    if (!item) return;
    void saveWebItem(
      { ask: (i) => placement.ask(i), save: (i, p) => search.save(i, p), toast: (t) => toasts.push(t), restore: restoreSaved({ api, navigate: (h) => router.navigate(h), toast: (t) => toasts.push(t) }) },
      item,
    );
  }
  // x on a chip: reject it (Undo toast), or undo a reject already made here.
  function chipX(tag: string, isRejected: boolean) {
    if (isRejected) {
      void api.unrejectTag(tag).then(
        () => (rejected = rejected.filter((t) => t !== tag)),
        () => toasts.push({ kind: "error", message: "Can't undo any more" }),
      );
      return;
    }
    rejected = [...rejected, tag];
    const clear = () => (rejected = rejected.filter((x) => x !== tag));
    const undoable: ToastsLike = {
      push: (t) => {
        if (t.kind !== "undo") clear();
        const act = t.onAction;
        return toasts.push({ ...t, onAction: () => { act?.(); clear(); } });
      },
    };
    void rejectTag(api, undoable, tag);
  }
  function openRow(r: { source: string; id: string }) {
    router.navigate("/web/" + encodeURIComponent(r.source) + "/" + encodeURIComponent(r.id));
  }
</script>

<BookPage
  ready={status === "ready" && !!book && !!item}
  cover={item?.thumb_url}
  backdrop={item?.thumb_url}
  title={names.big}
  sub={names.sub}
  onback={back}
>
  {#snippet read()}
    {#if count > 0}
      <button class="btn primary" type="button" onclick={() => router.navigate(readBase)}>
        <Icon name="book" size={20} />{last ? "Continue" : "Read"}
      </button>
    {/if}
  {/snippet}
  {#snippet actions()}
    {#if item}
      {#if saveState === "in_library" && savedHref}
        <a class="mi" role="menuitem" href={savedHref} onclick={(e) => linkClick(e, router)}><Icon name="check" size={20} />In library</a>
      {:else}
        <button class="mi" role="menuitem" type="button" disabled={saveState !== "idle" || item.saveable === false} onclick={save}>
          <span class:spin={saveState === "queued"}><Icon name={saveState === "queued" ? "loader" : saveState === "blocked" ? "alert" : "download"} size={20} /></span>
          {saveState === "queued" ? "Saving" : saveState === "blocked" ? "Blocked by a rule" : "Save"}
        </button>
      {/if}
      <a class="mi" role="menuitem" href={"https://nhentai.net/g/" + encodeURIComponent(id) + "/"} target="_blank" rel="noopener noreferrer"><Icon name="external-link" size={20} />Open on nhentai</a>
    {/if}
  {/snippet}
  {#snippet side()}
    {#each groups as [type, names] (type)}
      <section>
        <h2>{type}</h2>
        <TagChips
          tags={names.map((name) => ({ name, state: rejected.includes(name) ? ("rejected" as const) : undefined }))}
          mode="reject"
          onsearch={(name) => router.navigate(tagSearchHref(name, "web"))}
          onx={chipX}
        />
      </section>
    {/each}
    <SidePanel {source} {id} onopen={openRow} />
  {/snippet}

  {#if status === "loading"}
    <p class="note" role="status">Loading…</p>
  {:else if status === "error" || !book || !item}
    <div class="note">
      <p>{errorText}</p>
      <button class="btn" type="button" onclick={load}><Icon name="refresh" size={18} /> Retry</button>
    </div>
  {:else}
    {#if count > 0}
      <PageGrid thumbTpl={book.page_thumb_url} count={count} {last} hrefFor={(n) => readBase + "?p=" + n} />
    {:else}
      <p class="note">This book has no pages.</p>
    {/if}
  {/if}
</BookPage>

<style>
  h2 { margin: 0 0 var(--s-1); font-size: var(--t-12); text-transform: uppercase; color: var(--muted); letter-spacing: .04em; }
  section { margin-bottom: var(--s-4); }
  .note { text-align: center; color: var(--muted); padding: var(--s-5) 0; }
  .spin { display: inline-flex; animation: spin 1s linear infinite; }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @media (prefers-reduced-motion: reduce) {
    .spin { animation: none; }
  }
</style>
