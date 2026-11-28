<script lang="ts">
  import type { Snippet } from "svelte";

  let { title, text = "", action }: { title: string; text?: string; action?: Snippet } = $props();
</script>

<div class="flex flex-col items-center gap-2 px-4 py-10 text-center">
  <p class="text-base font-semibold">{title}</p>
  {#if text}<p class="max-w-[40ch] text-muted-foreground">{text}</p>{/if}
  {#if action}<div class="mt-2">{@render action()}</div>{/if}
</div>
