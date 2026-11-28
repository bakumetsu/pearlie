<script lang="ts">
  import { Tooltip } from "bits-ui";
  import type { Snippet } from "svelte";

  let { text, children }: { text: string; children: Snippet } = $props();
</script>

<!-- Rendered in place (no portal) so it stays inside .ui-root. Escape closes it. -->
<Tooltip.Provider delayDuration={300}>
  <Tooltip.Root>
    <Tooltip.Trigger class="inline-flex">{@render children()}</Tooltip.Trigger>
    <Tooltip.Content
      sideOffset={6}
      class="z-40 rounded-md border border-input bg-popover px-2.5 py-1.5 text-[13px] text-popover-foreground shadow-[var(--shadow-float)]"
      >{text}</Tooltip.Content
    >
  </Tooltip.Root>
</Tooltip.Provider>
