<script lang="ts">
  import { onMount } from "svelte";

  let h1: HTMLHeadingElement;

  onMount(() => h1.focus());
</script>

<section class="placeholder">
  <h1 tabindex="-1" bind:this={h1}>Option</h1>
  <p>Settings will live here</p>
</section>

<style>
  .placeholder {
    padding: var(--s-4);
  }

  .placeholder p {
    color: var(--muted);
  }
</style>
