<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils";

  // D-07 card (user 2026-11-28): 10 px radius, hairline border, flat. The title is an h3 like today's Options cards.
  let {
    title,
    description,
    class: className = "",
    children,
  }: { title?: string; description?: string; class?: string; children?: Snippet } = $props();
</script>

<section class={cn("rounded-lg border border-border bg-card px-4 py-1 text-card-foreground", className)}>
  {#if title}<h3 class="mb-0.5 mt-3 text-[15px] font-semibold">{title}</h3>{/if}
  {#if description}<p class="text-xs text-muted-foreground">{description}</p>{/if}
  {@render children?.()}
</section>
