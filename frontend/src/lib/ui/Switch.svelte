<script lang="ts">
  import { cn } from "$lib/utils";

  // Same contract as today's Switch.svelte: a button with role=switch; Space and Enter toggle (native button).
  let {
    checked,
    label,
    onclick,
    disabled = false,
    class: className = "",
  }: { checked: boolean; label: string; onclick: () => void; disabled?: boolean; class?: string } = $props();
</script>

<button
  type="button"
  role="switch"
  aria-checked={checked ? "true" : "false"}
  aria-label={label}
  {disabled}
  {onclick}
  class={cn(
    "group relative inline-flex h-11 min-w-12 shrink-0 items-center rounded-pill disabled:pointer-events-none disabled:opacity-50",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    className,
  )}
>
  <span class="block h-7 w-12 rounded-pill bg-input transition-colors duration-[120ms] group-aria-checked:bg-primary"></span>
  <span
    class="absolute left-[3px] top-[11px] size-[22px] rounded-full bg-muted-foreground transition-transform duration-[120ms] group-aria-checked:translate-x-5 group-aria-checked:bg-primary-foreground"
  ></span>
</button>
