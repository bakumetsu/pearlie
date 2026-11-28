<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils";

  // Media tile frame: thumbnail, caption, overlay. The browse Tile keeps its logic until the screen cards.
  let {
    src = "",
    alt = "",
    caption = "",
    ratio = "3/4",
    selected = false,
    onclick,
    overlay,
    class: className = "",
  }: {
    src?: string;
    alt?: string;
    caption?: string;
    ratio?: string;
    selected?: boolean;
    onclick?: () => void;
    overlay?: Snippet;
    class?: string;
  } = $props();
</script>

<div class={cn("relative overflow-hidden rounded-lg border border-border bg-card", selected && "border-primary", className)}>
  <button
    type="button"
    {onclick}
    aria-pressed={selected}
    aria-label={alt || caption}
    class="block min-h-11 w-full focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
    style:aspect-ratio={ratio}
  >
    {#if src}<img {src} {alt} loading="lazy" class="size-full object-cover" />{/if}
  </button>
  {#if caption}<div class="truncate px-2.5 py-2 text-[13px] text-muted-foreground">{caption}</div>{/if}
  {#if overlay}<div class="pointer-events-none absolute inset-x-0 top-0 p-2">{@render overlay()}</div>{/if}
</div>
