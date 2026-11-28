<script lang="ts">
  import type { Snippet } from "svelte";
  import TopTabBar from "./TopTabBar.svelte";
  import PhoneTopBar from "./PhoneTopBar.svelte";
  import PhoneBottomBar from "./PhoneBottomBar.svelte";
  import ToastRegion from "./ToastRegion.svelte";
  import { hidesBars } from "./nav";

  // Flag-on wrapper (VITE_UI_SHELL). Today's screens stay inside; no rail, so --rail-w is 0 here.
  let {
    current,
    queueBadge,
    onnavigate,
    children,
  }: { current: string; queueBadge?: number; onnavigate: (e: MouseEvent) => void; children: Snippet } = $props();

  const bars = $derived(!hidesBars(current));
</script>

<div class="ui-root min-h-dvh" style="--rail-w: 0px" data-shell>
  {#if bars}
    <TopTabBar {current} {queueBadge} {onnavigate} />
    <PhoneTopBar {current} />
    <PhoneBottomBar {current} {queueBadge} {onnavigate} />
  {/if}
  <div class={bars ? "pt-12 pb-14 lg:pb-0" : ""}>
    {@render children()}
  </div>
  <ToastRegion {bars} />
</div>
