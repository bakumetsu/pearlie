<script lang="ts">
  import Icon from "../components/Icon.svelte";

  let { value, onrate }: {
    value: number | null;
    onrate: (n: number) => void;
  } = $props();

  const stars: readonly number[] = [1, 2, 3, 4, 5];
</script>

<div role="radiogroup" aria-label="Rating" class="rs">
  {#each stars as n (n)}
    <button
      type="button"
      role="radio"
      aria-checked={value === n}
      aria-label="Rating {n} of 5"
      class:filled={value !== null && n <= value}
      onclick={() => onrate(n)}
    >
      <Icon name={value !== null && n <= value ? "star-filled" : "star"} size={20} />
    </button>
  {/each}
</div>

<style>
  .rs {
    display: flex;
    gap: var(--s-1);
  }
  button {
    background: transparent;
    border: none;
    color: var(--muted);
  }
  button.filled {
    color: var(--accent);
  }
</style>
