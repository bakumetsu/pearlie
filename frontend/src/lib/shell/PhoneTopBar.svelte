<script lang="ts">
  import IconButton from "$lib/ui/IconButton.svelte";
  import SfwEye from "./SfwEye.svelte";
  import { isDeep, titleFor } from "./nav";

  let { current }: { current: string } = $props();
</script>

<!-- Phone and tablet: 48 px bar with the page title, a back arrow on deep pages and the SFW eye. -->
<header class="fixed inset-x-0 top-0 z-[900] flex h-12 items-center gap-1 border-b border-border bg-background px-1 lg:hidden">
  {#if isDeep(current)}
    <IconButton icon="arrow-left" label="Back" onclick={() => history.back()} />
  {/if}
  <p class="min-w-0 flex-1 truncate px-2 text-base font-semibold">{titleFor(current)}</p>
  <SfwEye />
</header>
