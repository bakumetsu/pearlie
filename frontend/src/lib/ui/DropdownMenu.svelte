<script lang="ts">
  import { DropdownMenu } from "bits-ui";
  import type { Snippet } from "svelte";
  import { menuItemClass, menuPanelClass } from "./variants";
  import { cn } from "$lib/utils";

  type Option = { value: string; label: string };
  let {
    value = $bindable(""),
    options,
    label,
    trigger,
    onchange,
  }: { value?: string; options: Option[]; label: string; trigger: Snippet<[string]>; onchange?: (v: string) => void } = $props();
  const current = $derived(options.find((o) => o.value === value)?.label ?? "");
</script>

<!-- Menu button with radio items: arrows, Home, End move; Escape and outside tap close. -->
<DropdownMenu.Root>
  <DropdownMenu.Trigger
    aria-label={label}
    class="inline-flex h-11 min-w-11 items-center justify-center gap-2 rounded-md border border-input bg-card px-3 hover:bg-border focus-visible:outline-2 focus-visible:outline-ring"
    >{@render trigger(current)}</DropdownMenu.Trigger
  >
  <DropdownMenu.Content sideOffset={6} align="start" class={cn(menuPanelClass, "z-30")}>
    <DropdownMenu.RadioGroup bind:value onValueChange={(v) => onchange?.(v)}>
      {#each options as o (o.value)}
        <DropdownMenu.RadioItem value={o.value} class={cn(menuItemClass, "data-[highlighted]:bg-border")}>
          {#snippet children({ checked })}
            <span aria-checked={checked} class="contents">{o.label}</span>
          {/snippet}
        </DropdownMenu.RadioItem>
      {/each}
    </DropdownMenu.RadioGroup>
  </DropdownMenu.Content>
</DropdownMenu.Root>
