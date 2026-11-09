<script lang="ts">
  import { untrack } from "svelte";
  import { player } from "./player.svelte";

  let { id }: { id: string } = $props();

  let el: HTMLDivElement | undefined = undefined;

  $effect(() => {
    const node = el;
    if (!node) return;
    const slotId = id;

    const measure = () => {
      const r = node.getBoundingClientRect();
      untrack(() => player.setSlot(slotId, { x: r.x, y: r.y, w: r.width, h: r.height }));
    };

    measure();

    const ro = new ResizeObserver(measure);
    ro.observe(node);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);

    return () => {
      ro.disconnect();
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
      untrack(() => player.releaseSlot(slotId));
    };
  });
</script>

<div class="slot" bind:this={el}></div>

<style>
  .slot {
    width: 100%;
    height: 100%;
    background: transparent;
  }
</style>
