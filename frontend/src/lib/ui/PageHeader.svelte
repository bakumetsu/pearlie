<script lang="ts">
  import type { Snippet } from "svelte";

  let { title, actions }: { title: string; actions?: Snippet } = $props();
</script>

<header class="flex min-h-11 items-center justify-between gap-3">
  <h1 class="text-xl font-semibold">{title}</h1>
  {#if actions}<div class="flex items-center gap-2">{@render actions()}</div>{/if}
</header>
