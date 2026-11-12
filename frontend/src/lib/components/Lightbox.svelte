<script lang="ts">
  import { onMount } from "svelte";
  import type { WebItem } from "../api/client";
  import Icon from "./Icon.svelte";
  import SfwToggle from "./SfwToggle.svelte";
  import Backdrop from "./Backdrop.svelte";
  import { options } from "../stores/options.svelte";
  import { sfw } from "../stores/sfw.svelte";
  import { backdropStrength } from "../options/backdrop";

  let {
    item,
    saveState = "idle",
    savedHref,
    onsave,
    onreject,
    onclose,
  }: {
    item: WebItem;
    saveState?: "idle" | "queued" | "in_library" | "blocked";
    savedHref?: string;
    onsave: () => void;
    onreject?: (tag: string) => void;
    onclose: () => void;
  } = $props();

  let dialogEl: HTMLDialogElement;
  let openTagIdx = $state(-1);
  let previousFocus: HTMLElement | null = null;

  onMount(() => {
    previousFocus = document.activeElement as HTMLElement | null;
    dialogEl.showModal();
    return () => {
      previousFocus?.focus();
    };
  });

  const title = $derived(item.title ?? `${item.source} #${item.post_id}`);
  const backdrop = $derived(backdropStrength(options.values, "lightbox", sfw?.on ?? false));
</script>

<dialog
  bind:this={dialogEl}
  onclose={() => onclose()}
  onclick={(e) => {
    if (e.target === dialogEl) dialogEl.close();
  }}
>
  <Backdrop src={item.preview_url} strength={backdrop} />
  <SfwToggle />
  <div class="stage">
    <img src={item.preview_url} alt={item.title ?? ""} style="aspect-ratio: {item.width} / {item.height}; --ratio: {item.width / item.height};" />
  </div>

  <div class="panel">
    <header>
      <h2 class="title">{title}</h2>
      <button class="icon-btn" aria-label="Close" onclick={() => dialogEl.close()}>
        <Icon name="x" size={20} />
      </button>
    </header>

    {#if item.tags && item.tags.length}
      <section class="tags">
        <span class="tags-label">Tags</span>
        <ul>
          {#each item.tags as tag, i (tag.name)}
            <li>
              {#if onreject}
                <button
                  class="tag-btn"
                  onclick={() => (openTagIdx = openTagIdx === i ? -1 : i)}
                >
                  {tag.name}
                </button>
                {#if openTagIdx === i}
                  <div class="tag-menu">
                    <button
                      class="reject-btn"
                      onclick={() => {
                        onreject?.(tag.name);
                        openTagIdx = -1;
                      }}
                    >
                      Reject this tag
                    </button>
                  </div>
                {/if}
              {:else}
                <span class="tag-span">{tag.name}</span>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if saveState === "in_library"}
      <a class="save-btn in-library" href={savedHref}>
        <Icon name="check" size={18} />
        In library
      </a>
    {:else if saveState === "queued"}
      <button class="save-btn" disabled>
        <Icon name="loader" size={18} />
        Queued
      </button>
    {:else if saveState === "blocked"}
      <button class="save-btn blocked" disabled>
        <Icon name="alert" size={18} />
        Blocked by a rule
      </button>
    {:else}
      <button class="save-btn" onclick={onsave}>
        <Icon name="download" size={18} />
        Save
      </button>
    {/if}

    <p class="meta">Source: {item.source} · Post {item.post_id}</p>
  </div>
</dialog>

<style>
  .stage,
  .panel {
    position: relative;
    z-index: 1;
  }

  dialog {
    margin: auto;
    width: calc(100vw - 32px);
    height: calc(100vh - 32px);
    max-width: none;
    max-height: none;
    border: none;
    border-radius: var(--r-lg);
    background: var(--surface);
    padding: 0;
    display: flex;
    overflow: hidden;
  }

  dialog::backdrop {
    background: color-mix(in srgb, var(--bg) 80%, black);
  }

  .stage {
    flex: 1;
    min-width: 0;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    container-type: size;
  }

  .stage img {
    width: min(100cqw, calc(100cqh * var(--ratio)));
    height: auto;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .panel {
    width: 320px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
    padding: var(--s-4);
    border-left: 1px solid var(--line);
  }

  header {
    padding-right: calc(var(--sfw-inset) - var(--s-4));
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--s-2);
  }

  .title {
    flex: 1;
    min-width: 0;
    margin: 0;
    font-size: var(--t-15);
    font-weight: 600;
    color: var(--text);
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .icon-btn {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    border-radius: var(--r-md);
  }

  .icon-btn:hover {
    background: var(--accent-bg);
    color: var(--text);
  }

  .tags {
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
  }

  .tags-label {
    font-size: var(--t-12);
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .tags ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
  }

  .tags li {
    position: relative;
  }

  .tag-btn {
    display: block;
    width: 100%;
    text-align: left;
    padding: var(--s-1) var(--s-2);
    font-size: var(--t-13);
    color: var(--text);
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    cursor: pointer;
  }

  .tag-btn:hover {
    border-color: var(--line-strong);
  }

  .tag-span {
    display: block;
    padding: var(--s-1) var(--s-2);
    font-size: var(--t-13);
    color: var(--text);
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
  }

  .tag-menu {
    margin-top: var(--s-1);
    padding: var(--s-1);
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-md);
  }

  .reject-btn {
    display: block;
    width: 100%;
    padding: var(--s-1) var(--s-2);
    font-size: var(--t-12);
    color: var(--danger-fg);
    background: var(--danger-bg);
    border: none;
    border-radius: var(--r-md);
    cursor: pointer;
    text-align: left;
  }

  .save-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--s-2);
    width: 100%;
    min-height: 44px;
    padding: var(--s-3) var(--s-4);
    font-size: var(--t-14);
    font-weight: 500;
    color: var(--accent);
    background: var(--accent-bg);
    border: none;
    border-radius: var(--r-md);
    cursor: pointer;
    text-decoration: none;
    margin-top: auto;
  }

  .save-btn:hover:not(:disabled) {
    opacity: 0.88;
  }

  .save-btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .save-btn.in-library {
    color: var(--ok-fg);
    background: var(--ok-bg);
  }

  .save-btn.blocked {
    color: var(--danger-fg);
    background: var(--danger-bg);
  }

  .meta {
    margin: 0;
    font-size: var(--t-12);
    color: var(--muted);
  }
</style>
