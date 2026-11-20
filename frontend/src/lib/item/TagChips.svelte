<script lang="ts" module>
  export type ChipTag = { name: string; scope?: string; state?: "rejected" };
</script>

<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import { tick } from "svelte";

  const FOLD_AFTER = 8;

  let { tags, mode = "remove", inherited = [], readonly = false, onsearch, onx, onadd }: {
    tags: ChipTag[];
    mode?: "reject" | "remove";
    inherited?: ChipTag[];
    readonly?: boolean;
    onsearch?: (name: string) => void;
    onx?: (name: string, rejected: boolean) => void;
    onadd?: (name: string) => void;
  } = $props();

  type Entry = { tag: ChipTag; locked: boolean };

  // Own chips first; an inherited tag that is also own shows once, as own.
  const entries = $derived.by<Entry[]>(() => {
    const own = new Set(tags.map((t) => t.name));
    return [
      ...tags.map((tag) => ({ tag, locked: false })),
      ...inherited.filter((t) => !own.has(t.name)).map((tag) => ({ tag, locked: true })),
    ];
  });

  let expanded = $state(false);
  let adding = $state(false);
  let text = $state("");
  let root: HTMLElement | undefined = $state();
  let inputEl: HTMLInputElement | undefined = $state();

  const shown = $derived(expanded ? entries : entries.slice(0, FOLD_AFTER));
  const hidden = $derived(entries.length - shown.length);

  async function focusAfter(index: number): Promise<void> {
    await tick();
    const items = root?.querySelectorAll<HTMLElement>("[data-chip]");
    const target = items && items.length > 0 ? items[Math.min(index, items.length - 1)] : null;
    (target ?? root?.querySelector<HTMLElement>("[data-add]"))?.focus();
  }

  function handleX(entry: Entry, index: number): void {
    onx?.(entry.tag.name, entry.tag.state === "rejected");
    void focusAfter(index);
  }

  async function openAdd(): Promise<void> {
    adding = true;
    await tick();
    inputEl?.focus();
  }

  async function closeAdd(): Promise<void> {
    adding = false;
    text = "";
    await tick();
    root?.querySelector<HTMLElement>("[data-add]")?.focus();
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (e.key === "Enter") {
      e.preventDefault();
      const trimmed = text.trim();
      if (trimmed) {
        onadd?.(trimmed);
        void closeAdd();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      void closeAdd();
    }
  }

  function handleBlur(): void {
    if (adding && text.trim() === "") {
      adding = false;
      text = "";
    }
  }

  function xLabel(entry: Entry): string {
    if (entry.tag.state === "rejected") return `Undo reject ${entry.tag.name}`;
    return `${mode === "reject" ? "Reject" : "Remove"} ${entry.tag.name}`;
  }
</script>

<ul class="chips" bind:this={root}>
  {#each shown as entry, i (entry.tag.name)}
    {@const rejected = entry.tag.state === "rejected"}
    <li class="chip" class:rejected class:locked={entry.locked}>
      <button
        type="button"
        class="body"
        data-chip
        title={entry.locked ? "From a book in this series. Change it on the book." : undefined}
        aria-label={entry.locked ? `${entry.tag.name}. From a book in this series. Change it on the book.` : undefined}
        disabled={rejected}
        onclick={() => onsearch?.(entry.tag.name)}
      >
        {#if entry.locked}
          <svg class="lock" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="4" y="11" width="16" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 8 0v4" />
          </svg>
        {/if}
        <span class="name">{entry.tag.name}</span>
      </button>
      {#if !entry.locked && !readonly}
        <button type="button" class="x" aria-label={xLabel(entry)} onclick={() => handleX(entry, i)}>
          <Icon name={rejected ? "undo" : "x"} size={16} />
        </button>
      {/if}
    </li>
  {/each}
  {#if hidden > 0}
    <li class="item"><button type="button" class="more" onclick={() => (expanded = true)}>{hidden} more</button></li>
  {:else if expanded && entries.length > FOLD_AFTER}
    <li class="item"><button type="button" class="more" onclick={() => (expanded = false)}>Show less</button></li>
  {/if}
  {#if !readonly && onadd}
    <li class="item">
      {#if adding}
        <input
          class="add-input"
          type="text"
          aria-label="Add tag"
          placeholder="Add tag"
          bind:this={inputEl}
          bind:value={text}
          onkeydown={handleKeydown}
          onblur={handleBlur}
        />
      {:else}
        <button type="button" class="add" data-add aria-label="Add tag" onclick={openAdd}>
          <Icon name="plus" size={20} />
        </button>
      {/if}
    </li>
  {/if}
</ul>

<style>
  .chips {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
    margin: 0;
    padding: 0;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    background: var(--accent-bg);
    border: 1px solid var(--line);
    border-radius: 22px;
    font-size: var(--t-12);
    animation: fade 150ms ease-out;
  }
  .item {
    display: inline-flex;
    align-items: center;
    animation: fade 150ms ease-out;
  }
  button {
    background: transparent;
    border: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .body {
    display: inline-flex;
    align-items: center;
    gap: var(--s-1);
    min-height: 44px;
    padding: 0 var(--s-3);
    color: var(--text);
  }
  .chip:has(.x) .body {
    padding-right: 0;
  }
  .x {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    color: var(--muted);
  }
  .rejected {
    background: transparent;
  }
  .rejected .name {
    text-decoration: line-through;
    color: var(--muted);
  }
  .rejected .body {
    cursor: default;
  }
  .lock {
    flex: none;
  }
  .more {
    min-height: 44px;
    padding: 0 var(--s-3);
    border: 1px dashed var(--line);
    border-radius: 22px;
    color: var(--accent);
    font-size: var(--t-12);
  }
  .add {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border: 1px solid var(--line);
    border-radius: 50%;
    color: var(--muted);
  }
  .add-input {
    min-height: 44px;
    box-sizing: border-box;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 22px;
    color: var(--text);
    font-size: var(--t-14);
    padding: 0 var(--s-3);
  }
  .add-input::placeholder {
    color: var(--muted);
  }
  button:focus-visible,
  .add-input:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @media (prefers-reduced-motion: reduce) {
    .chip,
    .item {
      animation: none;
    }
  }
</style>
