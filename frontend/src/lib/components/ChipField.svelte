<script lang="ts">

  import type { Snippet } from "svelte";
  import type { Chip } from "../query";
  import { commitText, removeLastChip } from "../query";
  import Icon from "./Icon.svelte";

  let {
    chips,
    onchange,
    label,
    onsubmit,
    trailing,
  }: {
    chips: Chip[];
    onchange: (chips: Chip[]) => void;
    label?: string;
    onsubmit?: () => void;
    trailing?: Snippet;
  } = $props();

  let text = $state("");
  const labelId = "chipfield-label";
</script>

<div class="field" role="group" aria-labelledby={labelId}>
  <span id={labelId} class="sr-only">{label ?? "Search everything"}</span>
  <span class="search-icon"><Icon name="search" size={16} /></span>

  {#each chips as chip (chip.raw)}
    <span class="chip" class:exclude={chip.exclude}>
      {chip.raw}
      <button
        class="chip-remove"
        type="button"
        aria-label="Remove {chip.raw}"
        onclick={() => {
          onchange(chips.filter((c) => c.raw !== chip.raw));
        }}
      >
        <Icon name="x" size={12} />
      </button>
    </span>
  {/each}

  <input
    bind:value={text}
    class="chip-input"
    type="text"
    placeholder={chips.length === 0 ? "Search tags, e.g. cat -dog artist:x" : ""}
    autocomplete="off"
    onkeydown={(e) => {
      if ((e.key === "Enter" || e.key === ",") && text.trim()) {
        e.preventDefault();
        onchange(commitText(chips, text));
        text = "";
      } else if (e.key === "Enter" && !text.trim()) {
        e.preventDefault();
        onsubmit?.();
      } else if (e.key === "Backspace" && text === "") {
        onchange(removeLastChip(chips));
      }
    }}
    onpaste={(e) => {
      e.preventDefault();
      const pasted = e.clipboardData?.getData("text/plain") ?? "";
      if (pasted.trim()) onchange(commitText(chips, pasted));
    }}
    onblur={() => {
      if (text.trim()) {
        onchange(commitText(chips, text));
        text = "";
      }
    }}
  />
  {@render trailing?.()}
</div>

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

  .field {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-1);
    min-height: 44px;
    padding: var(--s-1) var(--s-2);
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-lg);
  }

  .field:focus-within {
    border-color: var(--accent);
  }

  .search-icon {
    display: flex;
    align-items: center;
    color: var(--muted);
    flex-shrink: 0;
  }

  .chip {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 2px 18px 2px var(--s-1);
    border-radius: var(--r-sm);
    background: var(--accent-bg);
    color: var(--accent);
    font-size: var(--t-13);
    line-height: 1.4;
  }

  .chip.exclude {
    background: var(--danger-bg);
    color: var(--danger-fg);
  }

  .chip-remove {
    position: absolute;
    top: 50%;
    left: 100%;
    transform: translate(-50%, -50%);
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    padding: 0;
    margin: 0;
    background: none;
    border: none;
    cursor: pointer;
    color: inherit;
    border-radius: var(--r-sm);
    z-index: 1;
  }

  .chip-remove:hover {
    background: color-mix(in oklab, var(--text) 10%, transparent);
  }

  .chip-input {
    flex: 1;
    min-width: 120px;
    min-height: 28px;
    padding: 4px 0;
    border: none;
    background: none;
    color: var(--text);
    font-size: var(--t-14);
    outline: none;
  }

  .chip-input::placeholder {
    color: var(--muted);
  }
</style>
