<script lang="ts">
  import type { Dir } from "./pages";
  import { segmentLayout, pageFromRatio } from "./pages";

  let { count, shown, dir, onjump }: {
    count: number;
    shown: number[];
    dir: Dir;
    onjump: (n: number) => void;
  } = $props();

  let trackWidth = $state(0);
  let dragging = $state(false);

  const layout = $derived(segmentLayout(count, trackWidth));
  const maxShown = $derived(shown.length ? Math.max(...shown) : 0);
  const shownSet = $derived(new Set(shown));
  const firstPage = $derived(shown[0] ?? 1);
  const fillPct = $derived(count > 1 ? ((maxShown - 1) / (count - 1)) * 100 : 0);

  function pageFromEvent(e: PointerEvent): number {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return pageFromRatio((e.clientX - rect.left) / rect.width, count, dir);
  }

  function onPointerDown(e: PointerEvent) {
    dragging = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    onjump(pageFromEvent(e));
  }
  function onPointerMove(e: PointerEvent) {
    if (!dragging) return;
    onjump(pageFromEvent(e));
  }
  function onPointerUp() { dragging = false; }

  function onKeyDown(e: KeyboardEvent) {
    let delta: number;
    if (e.key === "ArrowRight") delta = dir === "ltr" ? 1 : -1;
    else if (e.key === "ArrowLeft") delta = dir === "rtl" ? 1 : -1;
    else return;
    e.preventDefault();
    onjump(Math.min(Math.max(firstPage + delta, 1), count));
  }
</script>

<div
  class="pagebar"
  role="slider"
  aria-valuemin={1}
  aria-valuemax={count}
  aria-valuenow={firstPage}
  aria-valuetext="Page {firstPage} of {count}"
  tabindex={0}
  bind:clientWidth={trackWidth}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onkeydown={onKeyDown}
>
  {#if layout.kind === "segments"}
    <div class="segs" class:rtl={dir === "rtl"}>
      {#each Array.from({ length: layout.count }, (_, i) => i + 1) as p}
        <div
          class="seg"
          class:read={p <= maxShown && !shownSet.has(p)}
          class:cur={shownSet.has(p)}
          title="Page {p}"
        ></div>
      {/each}
    </div>
  {:else}
    <div class="track" class:rtl={dir === "rtl"}>
      <div class="fill" style="width:{fillPct}%"></div>
    </div>
  {/if}
</div>

<style>
  .pagebar {
    height: 44px;
    display: flex;
    align-items: center;
    min-width: 0;
    cursor: pointer;
    user-select: none;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    border-radius: 8px;
    font-size: var(--t-13, 13px);
  }
  .pagebar:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .segs {
    display: flex;
    gap: 2px;
    align-items: center;
    width: 100%;
    min-width: 0;
  }
  .segs.rtl { direction: rtl; }
  .seg {
    flex: 1;
    min-width: 0;
    height: 44px;
    position: relative;
  }
  .seg::before {
    content: "";
    position: absolute;
    left: 0; right: 0; top: 50%;
    height: 6px; margin-top: -3px;
    border-radius: 3px;
    background: var(--line-strong);
    transition: background 0.1s;
  }
  .seg.read::before { background: var(--accent); opacity: 0.4; }
  .seg.cur::before { background: var(--accent); opacity: 1; }
  .seg:hover::before { background: var(--accent); opacity: 0.7; }
  .seg:first-child::before { border-radius: 3px 0 0 3px; }
  .seg:last-child::before { border-radius: 0 3px 3px 0; }
  .track {
    position: relative;
    width: 100%;
    height: 6px;
    border-radius: 3px;
    background: var(--line-strong);
  }
  .track.rtl { direction: rtl; }
  .fill {
    position: absolute;
    top: 0; left: 0;
    height: 100%;
    border-radius: 3px;
    background: var(--accent);
  }
  .track.rtl .fill { left: auto; right: 0; }
</style>
