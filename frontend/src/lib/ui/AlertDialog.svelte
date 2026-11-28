<script lang="ts">
  import { AlertDialog } from "bits-ui";
  import { buttonVariants } from "./variants";

  let {
    open = $bindable(false),
    title,
    description,
    confirmLabel,
    cancelLabel = "Cancel",
    destructive = false,
    onconfirm,
  }: {
    open?: boolean;
    title: string;
    description: string;
    confirmLabel: string;
    cancelLabel?: string;
    destructive?: boolean;
    onconfirm: () => void;
  } = $props();
</script>

<!-- Focus is trapped, Escape cancels, an outside tap does not close it (an alert needs an answer). -->
<AlertDialog.Root bind:open>
  <AlertDialog.Overlay class="fixed inset-0 z-40 bg-scrim" />
  <AlertDialog.Content
    interactOutsideBehavior="ignore"
    class="fixed left-1/2 top-1/2 z-50 w-[min(420px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-input bg-popover p-5 text-popover-foreground shadow-[var(--shadow-float)]"
  >
    <AlertDialog.Title class="text-base font-semibold">{title}</AlertDialog.Title>
    <AlertDialog.Description class="mt-1 text-muted-foreground">{description}</AlertDialog.Description>
    <div class="mt-4 flex justify-end gap-2">
      <AlertDialog.Cancel class={buttonVariants({ variant: "outline" })}>{cancelLabel}</AlertDialog.Cancel>
      <AlertDialog.Action class={buttonVariants({ variant: destructive ? "destructive" : "default" })} onclick={onconfirm}
        >{confirmLabel}</AlertDialog.Action
      >
    </div>
  </AlertDialog.Content>
</AlertDialog.Root>
