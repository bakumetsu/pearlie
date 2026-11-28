<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils";

  let {
    open = $bindable(false),
    title,
    description = "",
    children,
    class: className = "",
  }: { open?: boolean; title: string; description?: string; children: Snippet; class?: string } = $props();
</script>

<!-- Escape closes; focus is trapped and returns to the opener. -->
<Dialog.Root bind:open>
  <Dialog.Overlay class="fixed inset-0 z-40 bg-scrim" />
  <Dialog.Content
    class={cn(
      "fixed left-1/2 top-1/2 z-50 w-[min(520px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-input bg-popover p-5 text-popover-foreground shadow-[var(--shadow-float)]",
      className,
    )}
  >
    <Dialog.Title class="text-base font-semibold">{title}</Dialog.Title>
    {#if description}<Dialog.Description class="mt-1 text-muted-foreground">{description}</Dialog.Description>{/if}
    <div class="mt-3">{@render children()}</div>
  </Dialog.Content>
</Dialog.Root>
