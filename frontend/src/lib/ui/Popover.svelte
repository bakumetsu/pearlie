<script lang="ts">
  import { Popover } from "bits-ui";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils";

  let {
    open = $bindable(false),
    label,
    trigger,
    children,
    class: className = "",
  }: { open?: boolean; label: string; trigger: Snippet; children: Snippet; class?: string } = $props();
</script>

<!-- Escape and outside tap close it; focus returns to the trigger. -->
<Popover.Root bind:open>
  <Popover.Trigger
    aria-label={label}
    class="inline-flex h-11 min-w-11 items-center justify-center gap-2 rounded-md border border-input px-3 hover:bg-border focus-visible:outline-2 focus-visible:outline-ring"
    >{@render trigger()}</Popover.Trigger
  >
  <Popover.Content
    sideOffset={6}
    class={cn("z-30 min-w-[220px] rounded-lg border border-input bg-popover p-3 text-popover-foreground shadow-[var(--shadow-float)]", className)}
    >{@render children()}</Popover.Content
  >
</Popover.Root>
