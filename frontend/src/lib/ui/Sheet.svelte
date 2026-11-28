<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils";

  // side "bottom" is the phone sheet; "right" is the desktop side panel.
  let {
    open = $bindable(false),
    title,
    side = "bottom",
    children,
    class: className = "",
  }: { open?: boolean; title: string; side?: "bottom" | "right"; children: Snippet; class?: string } = $props();
</script>

<Dialog.Root bind:open>
  <Dialog.Overlay class="fixed inset-0 z-40 bg-scrim" />
  <Dialog.Content
    class={cn(
      "fixed z-50 bg-popover p-4 text-popover-foreground shadow-[var(--shadow-float)]",
      side === "bottom"
        ? "inset-x-0 bottom-0 max-h-[85vh] overflow-auto rounded-t-lg border-t border-input"
        : "inset-y-0 right-0 w-[min(420px,100vw)] overflow-auto border-l border-input",
      className,
    )}
  >
    {#if side === "bottom"}<div class="mx-auto mb-3 h-1 w-10 rounded-pill bg-input"></div>{/if}
    <Dialog.Title class="mb-3 text-base font-semibold">{title}</Dialog.Title>
    {@render children()}
  </Dialog.Content>
</Dialog.Root>
