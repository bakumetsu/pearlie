<script lang="ts">
  import type { Snippet } from "svelte";
  import type { HTMLButtonAttributes } from "svelte/elements";
  import { cn } from "$lib/utils";
  import { buttonVariants } from "./variants";

  let {
    variant = "outline",
    size = "default",
    class: className = "",
    type = "button",
    children,
    ...rest
  }: HTMLButtonAttributes & {
    variant?: "default" | "outline" | "ghost" | "destructive" | "pill" | "chip";
    size?: "default" | "sm" | "icon";
    children?: Snippet;
  } = $props();
</script>

<button {type} class={cn(buttonVariants({ variant, size }), className)} {...rest}>
  {@render children?.()}
</button>
