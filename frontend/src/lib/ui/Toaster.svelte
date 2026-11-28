<script lang="ts">
  import { toasts } from "$lib/stores/toasts.svelte";
  import { cn } from "$lib/utils";

  // Wraps the existing toast store. Hover and focus pause the timer; undo toasts get 8 s from undoToast().
</script>

<div
  class="fixed inset-x-0 bottom-4 z-50 flex justify-center px-4"
  role="status"
  aria-live="polite"
  onmouseenter={() => toasts.pause()}
  onfocusin={() => toasts.pause()}
  onmouseleave={() => toasts.resume()}
  onfocusout={() => toasts.resume()}
>
  {#if toasts.current}
    {@const toast = toasts.current}
    <div
      class={cn(
        "flex min-h-11 items-center gap-3 rounded-lg border border-input bg-popover px-4 text-popover-foreground shadow-[var(--shadow-float)]",
        toast.kind === "error" && "border-destructive text-destructive",
      )}
    >
      <span>{toast.message}</span>
      {#if toast.actionLabel}
        {#if toast.href}
          <a
            href={toast.href}
            onclick={() => toasts.runAction()}
            class="inline-flex h-11 min-w-11 items-center font-semibold text-primary focus-visible:outline-2 focus-visible:outline-ring"
            >{toast.actionLabel}</a
          >
        {:else}
          <button
            type="button"
            onclick={() => toasts.runAction()}
            class="inline-flex h-11 min-w-11 items-center justify-center font-semibold text-primary focus-visible:outline-2 focus-visible:outline-ring"
            >{toast.actionLabel}</button
          >
        {/if}
      {/if}
    </div>
  {/if}
</div>
