<script lang="ts">
  import { tick } from "svelte";
  import type { SiteId } from "../query";
  import { SITE_ORDER, orderedSites, moveSite, toggleSiteIn } from "../query";

  let {
    sites,
    onsites,
    hidden = [],
    order,
    onreorder,
  }: {
    sites: SiteId[];
    onsites: (s: SiteId[]) => void;
    hidden?: readonly string[];
    order?: readonly string[];
    onreorder?: (order: SiteId[]) => void;
  } = $props();

  const MOVE_PX = 6;
  const HOLD_MS = 400;

  // Sites whose icon failed to load keep the letter mark.
  let broken = $state<Record<string, boolean>>({});
  // While a pill is dragged the rail shows the order it would get; it is saved once, on release.
  let preview = $state<SiteId[] | null>(null);
  let dragId = $state<SiteId | null>(null);
  const full = $derived(preview ?? orderedSites(order));
  const shown = $derived(full.map((id) => SITE_ORDER.find((s) => s.id === id)!).filter((s) => !hidden.includes(s.id)));

  let group: HTMLDivElement | undefined;
  let swallowClick = false;

  function pillAt(x: number): SiteId | null {
    let best: SiteId | null = null;
    let gap = Infinity;
    for (const el of group?.querySelectorAll<HTMLElement>("[data-site]") ?? []) {
      const r = el.getBoundingClientRect();
      const d = x >= r.left && x <= r.right ? 0 : Math.min(Math.abs(x - r.left), Math.abs(x - r.right));
      if (d < gap) {
        gap = d;
        best = el.dataset.site as SiteId;
      }
    }
    return best;
  }

  function startDrag(e: PointerEvent, id: SiteId): void {
    if (!onreorder || (e.pointerType === "mouse" && e.button !== 0)) return;
    const touch = e.pointerType !== "mouse";
    const x0 = e.clientX;
    const y0 = e.clientY;
    let active = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const stopScroll = (ev: TouchEvent) => {
      if (active) ev.preventDefault();
    };
    const begin = () => {
      active = true;
      dragId = id;
      preview = orderedSites(order);
    };
    const move = (ev: PointerEvent) => {
      if (!active) {
        if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < MOVE_PX) return;
        // A touch that moves before the hold is a scroll, not a drag.
        if (touch) return cancel();
        begin();
      }
      const over = pillAt(ev.clientX);
      if (over && preview && over !== dragId) {
        const next = moveSite(preview, id, over);
        if (next.join() !== preview.join()) preview = next;
      }
    };
    const finish = () => {
      const result = preview;
      const changed = active && result !== null && result.join() !== orderedSites(order).join();
      if (active) swallowClick = true;
      cancel();
      if (changed && result) onreorder?.(result);
    };
    const cancel = () => {
      if (timer !== null) clearTimeout(timer);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      group?.removeEventListener("touchmove", stopScroll);
      preview = null;
      dragId = null;
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    group?.addEventListener("touchmove", stopScroll, { passive: false });
    if (touch) timer = setTimeout(begin, HOLD_MS);
  }

  function onclick(id: SiteId): void {
    if (swallowClick) {
      swallowClick = false;
      return;
    }
    onsites(toggleSiteIn(sites, id));
  }

  async function onkeydown(e: KeyboardEvent, id: SiteId): Promise<void> {
    if (!onreorder || !e.altKey || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault();
    const visible = shown.map((s) => s.id);
    const at = visible.indexOf(id);
    const target = visible[at + (e.key === "ArrowLeft" ? -1 : 1)];
    if (!target) return;
    onreorder(moveSite(orderedSites(order), id, target));
    await tick();
    group?.querySelector<HTMLElement>(`[data-site="${id}"]`)?.focus();
  }
</script>

<div class="marks" role="group" aria-label="Sites" bind:this={group}>
  {#each shown as s (s.id)}
    {@const on = sites.includes(s.id)}
    <button
      class="mark-btn"
      class:dragging={dragId === s.id}
      type="button"
      data-site={s.id}
      title={onreorder ? `${s.label} (drag to reorder, Alt+arrows)` : s.label}
      aria-label={s.label}
      aria-pressed={on}
      aria-keyshortcuts={onreorder ? "Alt+ArrowLeft Alt+ArrowRight" : undefined}
      onpointerdown={(e) => startDrag(e, s.id)}
      onclick={() => onclick(s.id)}
      onkeydown={(e) => onkeydown(e, s.id)}
      oncontextmenu={(e) => dragId !== null && e.preventDefault()}
    >
      <span class="mark-visual" class:active={on}>
        {#if broken[s.id]}
          <span class="mk" aria-hidden="true">{s.label[0]}</span>
        {:else}
          <span class="mk" aria-hidden="true"
            ><img
              class="mk-img"
              data-sfw-shown="1"
              src={`/api/site-icons/${s.id}`}
              alt=""
              width="16"
              height="16"
              onerror={() => (broken[s.id] = true)}
            /></span
          >
        {/if}
        {#if on}<span class="mk-name">{s.label}</span>{/if}
      </span>
    </button>
  {/each}
</div>

<style>
  .marks {
    display: flex;
    gap: var(--s-1);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .mark-btn {
    display: grid;
    place-items: center;
    flex: none;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    border-radius: var(--r-md);
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }

  .mark-btn.dragging {
    opacity: 0.8;
    transform: scale(1.06);
    cursor: grabbing;
  }

  .mark-visual {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 10px;
    border-radius: var(--r-md);
    background: var(--surface);
    border: 1px solid var(--line);
    color: var(--muted);
    white-space: nowrap;
    font-size: var(--t-13);
  }

  .mark-visual.active {
    background: var(--accent-bg);
    border-color: var(--accent);
    color: var(--accent);
  }

  .mk {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: var(--line-strong);
    color: var(--text);
    font-size: 11px;
    font-weight: 700;
  }

  .mk-img {
    width: 16px;
    height: 16px;
    object-fit: contain;
  }

  .active .mk {
    background: var(--accent);
    color: var(--bg);
  }
</style>
