<script lang="ts">
  import { onMount } from "svelte";

  let h1: HTMLHeadingElement;

  onMount(() => h1.focus());
</script>

<section class="placeholder">
  <h1 tabindex="-1" bind:this={h1}>Home</h1>
  <p>Nothing here yet</p>
</section>

<style>
  .placeholder {
    padding: var(--s-4);
  }

  .placeholder p {
    color: var(--muted);
  }
</style>
