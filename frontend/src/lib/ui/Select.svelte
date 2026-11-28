<script lang="ts">
  import type { HTMLSelectAttributes } from "svelte/elements";
  import { cn } from "$lib/utils";
  import { fieldClass } from "./variants";

  // A native select: keeps the browser's own keys (arrows, Enter, Space, Escape, type-ahead).
  let { value = $bindable(), class: className = "", children, ...rest }: HTMLSelectAttributes = $props();
</script>

<select bind:value class={cn(fieldClass, "w-auto rounded-md bg-background px-2.5", className)} {...rest}>
  {@render children?.()}
</select>
