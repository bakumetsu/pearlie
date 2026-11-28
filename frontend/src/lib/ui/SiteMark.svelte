<script lang="ts">
  import { cn } from "$lib/utils";

  // Site icon from /api/site-icons/<id>; a failed load keeps the letter mark (as SiteMarks.svelte does).
  let { id, name, size = 20, class: className = "" }: { id: string; name: string; size?: number; class?: string } = $props();
  let broken = $state(false);
</script>

<span
  class={cn("inline-grid shrink-0 place-items-center overflow-hidden rounded-sm bg-muted text-[11px] font-semibold uppercase text-muted-foreground", className)}
  style:width="{size}px"
  style:height="{size}px"
  title={name}
>
  {#if broken}
    {name.charAt(0)}
  {:else}
    <img src={`/api/site-icons/${id}`} alt="" width={size} height={size} onerror={() => (broken = true)} />
  {/if}
</span>
