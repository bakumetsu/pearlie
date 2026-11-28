<script lang="ts">
  import type { HTMLInputAttributes } from "svelte/elements";
  import { cn } from "$lib/utils";
  import { fieldClass } from "./variants";

  let {
    value = $bindable(""),
    shape = "default",
    class: className = "",
    ...rest
  }: HTMLInputAttributes & { shape?: "default" | "pill" } = $props();
</script>

<input
  bind:value
  class={cn(fieldClass, shape === "pill" ? "rounded-pill px-3.5" : "rounded-md px-2.5", className)}
  {...rest}
/>
