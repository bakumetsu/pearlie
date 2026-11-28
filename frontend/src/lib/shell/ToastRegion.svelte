<script lang="ts">
  import { toasts, type Toast } from "$lib/stores/toasts.svelte";
  import { cn } from "$lib/utils";

  // Same store, labels and pause rules as ui/Toaster.svelte. Bottom centre on desktop; above the bottom bar on phone.
  // Stack of up to 3 from toasts.visible, Undo first. Only the current toast has a timer; each action runs its own toast.
  let { bars = true }: { bars?: boolean } = $props();

  function run(toast: Toast) {
    toast.onAction?.();
    toasts.dismiss(toast.id);
  }
</script>

<div
  class={cn("ui-root pointer-events-none bg-transparent! fixed inset-x-0 z-[1100] flex flex-col items-center gap-2 px-4", bars ? "bottom-[72px] lg:bottom-4" : "bottom-4")}
  role="status"
  aria-live="polite"
  aria-atomic="false"
  data-toast-region
>
  {#each toasts.visible as toast (toast.id)}
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
            onclick={() => run(toast)}
            class="inline-flex h-11 min-w-11 items-center font-semibold! text-primary! focus-visible:outline-2 focus-visible:outline-ring"
            >{toast.actionLabel}</a
          >
        {:else}
          <button
            type="button"
            onclick={() => run(toast)}
            class="inline-flex h-11 min-w-11 items-center justify-center font-semibold! text-primary! focus-visible:outline-2 focus-visible:outline-ring"
            >{toast.actionLabel}</button
          >
        {/if}
      {/if}
    </div>
  {/each}
</div>
