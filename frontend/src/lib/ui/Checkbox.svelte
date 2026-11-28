<script lang="ts">
  import type { HTMLInputAttributes } from "svelte/elements";
  import { cn } from "$lib/utils";

  // The label wraps the box, so the whole row is the 44 px target. Space toggles (native).
  let {
    checked = $bindable(false),
    label,
    class: className = "",
    ...rest
  }: Omit<HTMLInputAttributes, "type"> & { label: string } = $props();
</script>

<label class={cn("inline-flex min-h-11 cursor-pointer items-center gap-2.5", className)}>
  <input
    type="checkbox"
    bind:checked
    class="size-5 rounded-sm accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    {...rest}
  />
  <span>{label}</span>
</label>
