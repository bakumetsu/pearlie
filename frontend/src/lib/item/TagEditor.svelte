<script lang="ts">
  import Icon from "../components/Icon.svelte";

  let { tags, onadd, onremove, onreject }: {
    tags: string[];
    onadd: (text: string) => void;
    onremove: (tag: string) => void;
    onreject?: (tag: string) => void;
  } = $props();

  let text = $state("");

  function handleKeydown(e: KeyboardEvent): void {
    if (e.key === "Enter") {
      const trimmed = text.trim();
      if (trimmed) {
        onadd(trimmed);
        text = "";
      }
    }
  }
</script>

<ul class="chips">
  {#each tags as tag (tag)}
    <li class="chip">
      <span class="chip-text">{tag}</span>
      <button
        type="button"
        aria-label="Remove tag {tag}"
        onclick={() => onremove(tag)}
      >
        <Icon name="x" size={20} />
      </button>
      {#if onreject}
        <button
          type="button"
          class="reject"
          aria-label="Reject tag {tag}"
          onclick={() => onreject(tag)}
        >
          Reject
        </button>
      {/if}
    </li>
  {/each}
</ul>

<input
  type="text"
  placeholder="Add tag"
  aria-label="Add tag"
  bind:value={text}
  onkeydown={handleKeydown}
/>

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
    gap: var(--s-1);
    background: var(--accent-bg);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    padding: var(--s-1) var(--s-2);
    font-size: var(--t-12);
  }
  .chip-text {
    color: var(--text);
  }
  .chip button {
    background: transparent;
    border: none;
    color: var(--muted);
    display: inline-flex;
    align-items: center;
  }
  .reject {
    font-size: var(--t-12);
    color: var(--accent);
    padding: 0 var(--s-1);
  }
  input {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    color: var(--text);
    font-size: var(--t-14);
    padding: var(--s-2) var(--s-3);
    width: 100%;
  }
  input::placeholder {
    color: var(--muted);
  }
</style>
