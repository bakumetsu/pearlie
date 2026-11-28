<script lang="ts">
  import Icon from "$lib/components/Icon.svelte";
  import Badge from "$lib/ui/Badge.svelte";
  import SfwEye from "./SfwEye.svelte";
  import { TABS, isActive } from "./nav";

  let { current, queueBadge, onnavigate }: { current: string; queueBadge?: number; onnavigate: (e: MouseEvent) => void } = $props();
</script>

<!-- Desktop only: 48 px bar, 6 tabs (icon + word), accent tab has a 2 px underline, SFW eye at the right. -->
<header class="ui-root fixed inset-x-0 top-0 z-[900] hidden h-12 items-center border-b border-border bg-background px-2 lg:flex">
  <nav aria-label="Main" class="flex h-full flex-1 items-stretch gap-1">
    {#each TABS as tab (tab.name)}
      {@const active = isActive(tab.name, current)}
      <a
        href={tab.path}
        aria-current={active ? "page" : undefined}
        onclick={onnavigate}
        class="relative inline-flex min-h-11 min-w-11 items-center gap-2 self-center rounded-md px-3 text-[13px] text-muted-foreground! hover:bg-border hover:text-foreground! focus-visible:outline-2 focus-visible:outline-ring aria-[current=page]:text-primary!"
      >
        <Icon name={tab.icon} size={18} />
        <span>{tab.label}</span>
        {#if tab.name === "queue" && queueBadge && queueBadge > 0}
          <Badge variant="count">{queueBadge}</Badge>
        {/if}
        {#if active}<span class="absolute inset-x-2 -bottom-[3px] h-0.5 rounded-pill bg-primary" aria-hidden="true"></span>{/if}
      </a>
    {/each}
  </nav>
  <SfwEye />
</header>
