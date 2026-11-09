<script lang="ts">
  import { pageSrc } from "./pages";

  let { count, shown, template, wide = new Set<number>(), onjump }: {
    count: number;
    shown: number[];
    template: string | null;
    wide?: Set<number>;
    onjump: (n: number) => void;
  } = $props();

  const PAD = 8;
  const GAP = 8;
  const INSET = 4; // strip padding
  const slotW = (page: number) => (wide.has(page) ? 156 : 70) + GAP; // 3:2 for wide pages, 2:3 otherwise

  let stripEl: HTMLDivElement | null = $state(null);
  let lo = $state(0);
  let hi = $state(0);
  let broken = $state<Record<number, boolean>>({});
  // svelte-ignore state_referenced_locally
  let prevTpl = $state(template);

  function computeRange() {
    if (!stripEl) return;
    const sl = stripEl.scrollLeft;
    const cw = stripEl.clientWidth;
    let x = INSET;
    let first = -1;
    let last = count - 1;
    for (let i = 0; i < count; i++) {
      const end = x + slotW(i + 1);
      if (first < 0 && end > sl) first = i;
      if (x >= sl + cw) { last = i; break; }
      x = end;
    }
    if (first < 0) first = Math.max(0, count - 1);
    lo = Math.max(0, first - PAD);
    hi = Math.min(count - 1, last + PAD);
  }

  function onScroll() { computeRange(); }

  function onErr(e: Event) {
    broken[+(e.currentTarget as HTMLElement).dataset.page!] = true;
  }

  $effect(() => {
    void wide;
    if (template !== prevTpl) {
      prevTpl = template;
      broken = {};
    }
    computeRange();
    const el = stripEl;
    if (!el) return;
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  });

  $effect(() => {
    const cur = shown[0];
    if (cur === undefined || !stripEl) return;
    const btn = stripEl.querySelector(`[data-page="${cur}"]`) as HTMLElement | null;
    btn?.scrollIntoView?.({ inline: "center", block: "nearest" });
  });
</script>

<div class="strip" data-testid="thumb-strip" bind:this={stripEl}>
  {#each Array.from({ length: count }, (_, i) => i) as i (i)}
    <button
      class="thumb" class:on={shown.includes(i + 1)} class:wide={wide.has(i + 1)}
      aria-label="Page {i + 1}" data-page={i + 1}
      onclick={() => onjump(i + 1)}
    >
      <span class="num">{i + 1}</span>
      {#if template && i >= lo && i <= hi && !broken[i + 1]}
        <img
          src={pageSrc(template, i + 1)}
          alt="" loading="lazy"
          data-page={i + 1} onerror={onErr}
        />
      {/if}
    </button>
  {/each}
</div>

<style>
  .strip {
    position: absolute;
    bottom: 76px;
    left: 50%;
    transform: translateX(-50%);
    width: min(720px, calc(100% - 32px));
    border-radius: 12px;
    display: flex;
    gap: var(--s-2, 8px);
    overflow-x: auto;
    overflow-y: hidden;
    padding: 4px;
    scrollbar-width: thin;
    scrollbar-color: var(--line-strong, #34343b) transparent;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    font-size: var(--t-13, 13px);
  }
  .thumb {
    position: relative;
    flex: none;
    width: 70px;
    height: 104px;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    border: 2px solid transparent;
    border-radius: var(--r-sm, 6px);
    background: #4a4a52;
    cursor: pointer;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .thumb.wide { width: 156px; }
  .thumb.on {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .thumb:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .num {
    color: var(--text, #ececef);
    font-size: 14px;
    font-variant-numeric: tabular-nums;
  }
  img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    pointer-events: none;
  }
</style>
