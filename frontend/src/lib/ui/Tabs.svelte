<script lang="ts">
  import { Tabs } from "bits-ui";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils";

  type Tab = { value: string; label: string };
  let {
    value = $bindable(""),
    tabs,
    label,
    panel,
    class: className = "",
  }: { value?: string; tabs: Tab[]; label: string; panel?: Snippet<[string]>; class?: string } = $props();
</script>

<!-- Arrow keys, Home and End move between tabs (bits-ui roving focus). -->
<Tabs.Root bind:value class={className}>
  <Tabs.List aria-label={label} class="flex gap-1 border-b border-border">
    {#each tabs as t (t.value)}
      <Tabs.Trigger
        value={t.value}
        class={cn(
          "inline-flex h-11 min-w-11 items-center justify-center border-b-2 border-transparent px-4 text-muted-foreground",
          "hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring data-[state=active]:border-primary data-[state=active]:text-primary",
        )}>{t.label}</Tabs.Trigger
      >
    {/each}
  </Tabs.List>
  {#each tabs as t (t.value)}
    <Tabs.Content value={t.value} class="pt-3">{@render panel?.(t.value)}</Tabs.Content>
  {/each}
</Tabs.Root>
