<script lang="ts">
  import Icon from "$lib/components/Icon.svelte";
  import Badge from "$lib/ui/Badge.svelte";
  import { TABS, isActive } from "./nav";

  let { current, queueBadge, onnavigate }: { current: string; queueBadge?: number; onnavigate: (e: MouseEvent) => void } = $props();
</script>

<!-- Phone and tablet: 56 px bar, 6 items, 11 px labels. -->
<nav
  aria-label="Main"
  class="ui-root fixed inset-x-0 bottom-0 z-[900] flex h-14 items-stretch justify-evenly border-t border-border bg-background lg:hidden"
>
  {#each TABS as tab (tab.name)}
    {@const active = isActive(tab.name, current)}
    <a
      href={tab.path}
      aria-current={active ? "page" : undefined}
      onclick={onnavigate}
      class="relative inline-flex min-h-11 min-w-11 flex-1 flex-col items-center justify-center gap-1 text-muted-foreground! focus-visible:outline-2 focus-visible:outline-ring aria-[current=page]:text-primary!"
    >
      <Icon name={tab.icon} size={20} />
      <span class="text-[11px] leading-none">{tab.label}</span>
      {#if tab.name === "queue" && queueBadge && queueBadge > 0}
        <Badge variant="count" class="absolute top-1 right-[calc(50%-24px)]">{queueBadge}</Badge>
      {/if}
    </a>
  {/each}
</nav>
