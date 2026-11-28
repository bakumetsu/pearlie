<script lang="ts">
  import type { HTMLInputAttributes } from "svelte/elements";
  import { cn } from "$lib/utils";

  // A native range: keeps arrows, Home, End, PageUp and PageDown. The accent colours the whole track.
  let { value = $bindable(0), class: className = "", ...rest }: Omit<HTMLInputAttributes, "type"> = $props();
</script>

<input
  type="range"
  bind:value
  class={cn("h-11 w-[200px] max-w-[50vw] accent-primary focus-visible:outline-2 focus-visible:outline-ring", className)}
  {...rest}
/>
