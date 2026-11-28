<script lang="ts">
  import type { Snippet } from "svelte";
  import { tv } from "tailwind-variants";
  import { cn } from "$lib/utils";

  const badge = tv({
    base: "inline-flex items-center gap-1 text-xs",
    variants: {
      variant: {
        accent: "rounded-pill bg-accent px-2 py-px text-primary",
        ok: "rounded-pill bg-ok/15 px-2 py-px text-ok",
        danger: "rounded-pill bg-destructive/15 px-2 py-px text-destructive",
        count: "h-[18px] min-w-[18px] justify-center rounded-[9px] bg-primary px-[5px] text-[11px] font-semibold text-primary-foreground",
      },
    },
    defaultVariants: { variant: "accent" },
  });
  let {
    variant = "accent",
    class: className = "",
    children,
  }: { variant?: "accent" | "ok" | "danger" | "count"; class?: string; children?: Snippet } = $props();
</script>

<span class={cn(badge({ variant }), className)}>{@render children?.()}</span>
