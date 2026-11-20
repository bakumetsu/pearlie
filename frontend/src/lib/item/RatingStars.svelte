<script lang="ts">
  import Icon from "../components/Icon.svelte";

  let { value, onrate, size = 20 }: {
    value: number | null;
    size?: number;
    onrate: (n: number) => void;
  } = $props();

  const stars: readonly number[] = [1, 2, 3, 4, 5];
</script>

<div role="radiogroup" aria-label="Rating" class="rs" class:big={size > 20}>
  {#each stars as n (n)}
    <button
      type="button"
      role="radio"
      aria-checked={value === n}
      aria-label="Rating {n} of 5"
      class:filled={value !== null && n <= value}
      onclick={() => onrate(n)}
    >
      <Icon name={value !== null && n <= value ? "star-filled" : "star"} {size} />
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
    min-height: 44px;
    min-width: 32px;
    padding: 0;
    cursor: pointer;
  }
  /* Big stars sit in the narrow hero by-line: keep the row inside a phone column; the height stays 44 px. */
  .big { gap: 0; max-width: 100%; }
  .big button { flex: 0 1 28px; min-width: 0; padding: 0; display: grid; place-items: center; overflow: hidden; }
  button.filled {
    color: var(--accent);
  }
</style>
