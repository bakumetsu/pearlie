<script lang="ts">
  import { toasts } from "$lib/stores/toasts.svelte";
  import { cn } from "$lib/utils";

  // Same store, labels and pause rules as ui/Toaster.svelte. Bottom centre on desktop; above the bottom bar on phone.
  // The store shows one toast at a time and queues the rest (toasts.svelte.ts:13-14): the queue shows as "+N".
  let { bars = true }: { bars?: boolean } = $props();
</script>

<div
  class={cn("pointer-events-none fixed inset-x-0 z-[1100] flex justify-center px-4", bars ? "bottom-[72px] lg:bottom-4" : "bottom-4")}
  role="status"
  aria-live="polite"
  aria-atomic="false"
  data-toast-region
>
  {#if toasts.current}
    {@const toast = toasts.current}
    <div
      class={cn(
        "pointer-events-auto flex min-h-11 max-w-full items-center gap-3 rounded-lg border border-input bg-popover px-4 text-popover-foreground shadow-[var(--shadow-float)]",
        toast.kind === "error" && "border-destructive text-destructive",
      )}
      role="presentation"
      onmouseenter={() => toasts.pause()}
      onfocusin={() => toasts.pause()}
      onmouseleave={() => toasts.resume()}
      onfocusout={() => toasts.resume()}
    >
      <span class="min-w-0">{toast.message}</span>
      {#if toast.actionLabel}
        {#if toast.href}
          <a
            href={toast.href}
            onclick={() => toasts.runAction()}
            class="inline-flex h-11 min-w-11 items-center font-semibold! text-primary! focus-visible:outline-2 focus-visible:outline-ring"
            >{toast.actionLabel}</a
          >
        {:else}
          <button
            type="button"
            onclick={() => toasts.runAction()}
            class="inline-flex h-11 min-w-11 items-center justify-center font-semibold! text-primary! focus-visible:outline-2 focus-visible:outline-ring"
            >{toast.actionLabel}</button
          >
        {/if}
      {/if}
      {#if toasts.queued > 0}
        <span class="text-xs text-muted-foreground" aria-label="{toasts.queued} more">+{toasts.queued}</span>
      {/if}
    </div>
  {/if}
</div>
