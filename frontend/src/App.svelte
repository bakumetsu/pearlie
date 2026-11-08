<script lang="ts">
  import { onMount } from "svelte";
  import { getHealth } from "./lib/api";

  let status = $state("Loading…");

  onMount(() => {
    getHealth()
      .then((h) => {
        status = `Backend: ${h.status}`;
      })
      .catch(() => {
        status = "Backend unreachable";
      });
  });
</script>

<header>Pearlie</header>
<p>{status}</p>

<style>
  :global(body) {
    font-family: system-ui, sans-serif;
    margin: 0;
    padding: 1rem;
  }
  :global(button) {
    min-height: 44px;
  }
</style>
