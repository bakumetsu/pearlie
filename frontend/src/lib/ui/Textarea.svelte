<script lang="ts">
  import type { HTMLTextareaAttributes } from "svelte/elements";
  import { cn } from "$lib/utils";
  import { fieldClass } from "./variants";

  let { value = $bindable(""), class: className = "", ...rest }: HTMLTextareaAttributes = $props();
</script>

<textarea
  bind:value
  class={cn(fieldClass, "h-auto min-h-[88px] rounded-md px-2.5 py-2", className)}
  {...rest}
></textarea>
