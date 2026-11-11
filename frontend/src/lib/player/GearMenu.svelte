<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import { player, RATES } from "./player.svelte";
  import { playerSettings } from "./playerSettings.svelte";
  import { tick } from "svelte";

  let open = $state(false);
  let page = $state<"main" | "speed" | "quality">("main");
  let root: HTMLDivElement | null = $state(null);
  let trigger: HTMLButtonElement | null = $state(null);
  let drag = { x: 0, active: false, moved: false };
  let suppressClick = false;

  function getRows(): HTMLElement[] {
    if (!root) return [];
    return Array.from(
      root.querySelectorAll<HTMLElement>('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"]')
    );
  }

  function focusRow(idx: number): void {
    const list = getRows();
    if (list.length === 0) return;
    const clamped = ((idx % list.length) + list.length) % list.length;
    list[clamped]?.focus();
  }

  function close(): void {
    open = false;
  }

  function toggleOpen(): void {
    if (!open) page = "main";
    open = !open;
  }

  function openPage(p: "speed" | "quality"): void {
    page = p;
    void tick().then(() => {
      if (p === "speed") {
        const rIdx = (RATES as readonly number[]).indexOf(player.rate);
        focusRow(rIdx >= 0 ? rIdx + 1 : 1);
      } else {
        const sIdx = player.sourceIdx;
        focusRow(sIdx >= 0 ? sIdx + 2 : 1);
      }
    });
  }

  function backToMain(openIdx: number): void {
    page = "main";
    void tick().then(() => {
      focusRow(openIdx);
    });
  }

  function swallowNextClick(): void {
    const g = (ev: Event) => {
      ev.stopPropagation();
      ev.preventDefault();
      window.removeEventListener("click", g, true);
    };
    window.addEventListener("click", g, true);
    setTimeout(() => window.removeEventListener("click", g, true), 400);
  }

  function onSwitchDown(e: PointerEvent): void {
    drag = { x: e.clientX, active: true, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function onSwitchMove(e: PointerEvent): void {
    if (!drag.active) return;
    if (Math.abs(e.clientX - drag.x) > 12) drag.moved = true;
  }

  function onSwitchUp(e: PointerEvent, current: boolean, apply: () => void): void {
    if (!drag.active) return;
    drag.active = false;
    const dx = e.clientX - drag.x;
    if (drag.moved) {
      suppressClick = true;
      if (current ? dx < -18 : dx > 18) apply();
      drag.moved = false;
    }
  }

  function onSwitchClick(apply: () => void): void {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    apply();
  }

  $effect(() => {
    if (!open) return;

    void tick().then(() => {
      if (open) focusRow(0);
    });

    const stopSet = new Set([
      "j", "J", "l", "L", " ", "<", ">",
      "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
    ]);

    function onKeyDown(e: KeyboardEvent) {
      const key = e.key;
      const list = getRows();
      if (list.length === 0) return;

      const cur = list.indexOf(document.activeElement as HTMLElement);

      const shiftNP = e.shiftKey && (key === "n" || key === "N" || key === "p" || key === "P");
      if (
        stopSet.has(key) ||
        key === "Home" || key === "End" || key === "Enter" ||
        key === "ArrowRight" || key === "ArrowLeft" || key === "Backspace" || key === "Escape" ||
        shiftNP
      ) {
        e.stopPropagation();
      }

      const inRoot = root?.contains(document.activeElement) ?? false;

      const speedRowIdx = 2;
      const qualityRowIdx = 3;
      const onSub = page === "speed" || page === "quality";
      const openerIdx = page === "speed" ? speedRowIdx : qualityRowIdx;

      switch (key) {
        case "ArrowDown":
          if (inRoot) focusRow(cur + 1);
          break;
        case "ArrowUp":
          if (inRoot) focusRow(cur - 1);
          break;
        case "Home":
          if (inRoot) focusRow(0);
          break;
        case "End":
          if (inRoot) focusRow(list.length - 1);
          break;
        case "Enter":
        case " ":
          if (inRoot) {
            e.preventDefault();
            (document.activeElement as HTMLElement).click();
          }
          break;
        case "ArrowRight":
          if (inRoot && page === "main") {
            if (cur === speedRowIdx) openPage("speed");
            else if (cur === qualityRowIdx) openPage("quality");
          }
          break;
        case "ArrowLeft":
        case "Backspace":
          if (inRoot && onSub) backToMain(openerIdx);
          break;
        case "Escape":
          if (onSub) backToMain(openerIdx);
          else {
            close();
            trigger?.focus();
          }
          break;
      }
    }

    function onPointerDown(e: PointerEvent) {
      if (!root?.contains(e.target as Node)) {
        close();
        swallowNextClick();
      }
    }

    function onFocusOut(e: FocusEvent): void {
      const next = e.relatedTarget as Node | null;
      if (next && !root?.contains(next)) close();
    }

    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("pointerdown", onPointerDown, true);
    root?.addEventListener("focusout", onFocusOut);

    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("pointerdown", onPointerDown, true);
      root?.removeEventListener("focusout", onFocusOut);
    };
  });
</script>

<div class="gear" bind:this={root}>
  <button
    class="btn"
    bind:this={trigger}
    aria-label="Player settings"
    aria-haspopup="menu"
    aria-expanded={open}
    onclick={toggleOpen}
  >
    <Icon name="settings" size={20} />
  </button>

  {#if open}
    <div class="pop" role="menu" aria-label="Player settings">
      {#if page === "main"}
        <div class="page" role="none">
          <button
            class="row switch-row"
            role="menuitemcheckbox"
            aria-checked={playerSettings.autoplay}
            tabindex={0}
            onpointerdown={onSwitchDown}
            onpointermove={onSwitchMove}
            onpointerup={(e) => onSwitchUp(e, playerSettings.autoplay, () => void playerSettings.setAutoplay(!playerSettings.autoplay))}
            onclick={() => onSwitchClick(() => void playerSettings.setAutoplay(!playerSettings.autoplay))}
          >
            <span>Autoplay</span>
            <span class="track" class:on={playerSettings.autoplay}><span class="thumb"></span></span>
          </button>
          <button
            class="row switch-row"
            role="menuitemcheckbox"
            aria-checked={player.loop}
            tabindex={-1}
            onpointerdown={onSwitchDown}
            onpointermove={onSwitchMove}
            onpointerup={(e) => onSwitchUp(e, player.loop, () => player.setLoop(!player.loop))}
            onclick={() => onSwitchClick(() => player.setLoop(!player.loop))}
          >
            <span>Loop</span>
            <span class="track" class:on={player.loop}><span class="thumb"></span></span>
          </button>
          <button
            class="head"
            role="menuitem"
            aria-haspopup="menu"
            tabindex={-1}
            onclick={() => openPage("speed")}
          >
            <span>Speed</span>
            <span class="value">{player.rate === 1 ? "Normal" : player.rate + "x"}</span>
            <Icon name="chevron-right" size={16} />
          </button>
          {#if (player.item?.fallbacks ?? []).length > 0}
            <button
              class="head"
              role="menuitem"
              aria-haspopup="menu"
              tabindex={-1}
              onclick={() => openPage("quality")}
            >
              <span>Quality</span>
              <span class="value">{player.sourceIdx === -1 ? "Direct" : (player.item?.fallbacks?.[player.sourceIdx]?.label || "Option " + (player.sourceIdx + 1))}</span>
              <Icon name="chevron-right" size={16} />
            </button>
          {/if}
        </div>
      {:else if page === "speed"}
        <div class="page" role="none">
          <button
            class="head"
            role="menuitem"
            aria-label="Back to settings"
            tabindex={0}
            onclick={() => backToMain(2)}
          >
            <Icon name="chevron-left" size={16} />
            <span>Speed</span>
          </button>
          {#each RATES as r (r)}
            <button
              class="opt"
              class:current={player.rate === r}
              role="menuitemradio"
              aria-checked={player.rate === r}
              tabindex={-1}
              onclick={() => { player.setRate(r); backToMain(2); }}
            >
              <span class="mark">{#if player.rate === r}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
              {r}x
            </button>
          {/each}
        </div>
      {:else if page === "quality"}
        <div class="page" role="none">
          <button
            class="head"
            role="menuitem"
            aria-label="Back to settings"
            tabindex={0}
            onclick={() => backToMain(3)}
          >
            <Icon name="chevron-left" size={16} />
            <span>Quality</span>
          </button>
          <button
            class="opt"
            class:current={player.sourceIdx === -1}
            role="menuitemradio"
            aria-checked={player.sourceIdx === -1}
            tabindex={-1}
            onclick={() => { player.setQuality(-1); backToMain(3); }}
          >
            <span class="mark">{#if player.sourceIdx === -1}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
            Direct
          </button>
          {#each (player.item?.fallbacks ?? []) as fb, i (i)}
            <button
              class="opt"
              class:current={player.sourceIdx === i}
              role="menuitemradio"
              aria-checked={player.sourceIdx === i}
              tabindex={-1}
              onclick={() => { player.setQuality(i); backToMain(3); }}
            >
              <span class="mark">{#if player.sourceIdx === i}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
              {fb.label || "Option " + (i + 1)}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .gear {
    display: contents;
  }

  .btn {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    background: transparent;
    border: none;
    border-radius: var(--r-sm);
    color: var(--text);
    cursor: pointer;
    padding: 0;
  }

  .btn:hover {
    background: var(--line);
  }

  .pop {
    position: absolute;
    bottom: 100%;
    right: 0;
    width: 260px;
    max-width: calc(100% - 16px);
    max-height: min(60vh, 100%);
    overflow-y: auto;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    z-index: 23;
    display: flex;
    flex-direction: column;
    padding: var(--s-1);
    box-sizing: border-box;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 44px;
    width: 100%;
    background: transparent;
    border: none;
    border-radius: var(--r-sm);
    color: var(--text);
    cursor: pointer;
    padding: 0 var(--s-1);
    font-size: var(--t-12);
    font-weight: 600;
    box-sizing: border-box;
  }

  .head:hover {
    background: var(--line);
  }

  .opt {
    display: flex;
    align-items: center;
    min-height: 44px;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    border-radius: var(--r-sm);
    color: var(--text);
    cursor: pointer;
    padding: 0 var(--s-1);
    font-size: var(--t-12);
    box-sizing: border-box;
    gap: var(--s-1);
  }

  .opt:hover {
    background: var(--line);
  }

  .opt.current {
    color: var(--accent);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 44px;
    width: 100%;
    background: transparent;
    border: none;
    border-radius: var(--r-sm);
    color: var(--text);
    cursor: pointer;
    padding: 0 var(--s-1);
    font-size: var(--t-12);
    font-weight: 400;
    box-sizing: border-box;
  }

  .row:hover {
    background: var(--line);
  }

  .value {
    margin-left: auto;
    color: var(--muted, var(--text));
  }

  .track {
    position: relative;
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background: var(--line);
    transition: background 120ms;
    flex-shrink: 0;
  }

  .track.on {
    background: var(--accent);
  }

  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #fff;
    transition: transform 120ms;
  }

  .track.on .thumb {
    transform: translateX(16px);
  }

  .page {
    animation: pagein 150ms ease-out;
  }

  @keyframes pagein {
    from {
      opacity: 0;
      transform: translateX(12px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .mark {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .spacer {
    display: block;
    width: 16px;
    height: 16px;
  }

  .row:focus-visible,
  .head:focus-visible,
  .opt:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  @media (prefers-reduced-motion: reduce) {
    .track,
    .thumb {
      transition: none;
    }
    .page {
      animation: none;
    }
  }
</style>
