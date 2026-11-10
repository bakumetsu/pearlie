<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import { player, RATES } from "./player.svelte";

  let open = $state(false);
  let root: HTMLDivElement | null = $state(null);
  let trigger: HTMLButtonElement | null = $state(null);

  let expanded = $state({ speed: true, quality: false, loop: false });

  function close(): void {
    open = false;
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

  function toggleSection(key: "speed" | "quality" | "loop"): void {
    expanded[key] = !expanded[key];
  }

  $effect(() => {
    if (!open) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        trigger?.focus();
      } else if (e.key === "j" || e.key === "J" || e.key === "l" || e.key === "L" || e.key === " ") {
        e.stopPropagation();
      }
    }

    function onPointerDown(e: PointerEvent) {
      if (!root?.contains(e.target as Node)) {
        close();
        swallowNextClick();
      }
    }

    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("pointerdown", onPointerDown, true);

    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("pointerdown", onPointerDown, true);
    };
  });
</script>

<div class="gear" bind:this={root}>
  <button
    class="btn"
    bind:this={trigger}
    aria-label="Player settings"
    aria-haspopup="true"
    aria-expanded={open}
    onclick={() => { open = !open; }}
  >
    <Icon name="settings" size={20} />
  </button>

  {#if open}
    <div class="pop" role="group" aria-label="Player settings">
      <!-- Speed -->
      <button class="head" aria-expanded={expanded.speed} onclick={() => toggleSection("speed")}>
        <span>Speed</span>
        <Icon name={expanded.speed ? "chevron-up" : "chevron-down"} size={16} />
      </button>
      {#if expanded.speed}
        <div class="body">
          {#each RATES as r (r)}
            <button
              class="opt"
              class:current={player.rate === r}
              aria-pressed={player.rate === r}
              onclick={() => { player.setRate(r); close(); }}
            >
              <span class="mark">{#if player.rate === r}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
              {r}x
            </button>
          {/each}
        </div>
      {/if}

      <!-- Quality -->
      <button class="head" aria-expanded={expanded.quality} onclick={() => toggleSection("quality")}>
        <span>Quality</span>
        <Icon name={expanded.quality ? "chevron-up" : "chevron-down"} size={16} />
      </button>
      {#if expanded.quality}
        <div class="body">
          <button
            class="opt"
            class:current={player.sourceIdx === -1}
            aria-pressed={player.sourceIdx === -1}
            onclick={() => { player.setQuality(-1); close(); }}
          >
            <span class="mark">{#if player.sourceIdx === -1}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
            Direct
          </button>
          {#each (player.item?.fallbacks ?? []) as fb, i (i)}
            <button
              class="opt"
              class:current={player.sourceIdx === i}
              aria-pressed={player.sourceIdx === i}
              onclick={() => { player.setQuality(i); close(); }}
            >
              <span class="mark">{#if player.sourceIdx === i}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
              {fb.label || "Option " + (i + 1)}
            </button>
          {/each}
        </div>
      {/if}

      <!-- Loop -->
      <button class="head" aria-expanded={expanded.loop} onclick={() => toggleSection("loop")}>
        <span>Loop</span>
        <Icon name={expanded.loop ? "chevron-up" : "chevron-down"} size={16} />
      </button>
      {#if expanded.loop}
        <div class="body">
          <button
            class="opt"
            class:current={player.loop === false}
            aria-pressed={player.loop === false}
            onclick={() => { player.setLoop(false); close(); }}
          >
            <span class="mark">{#if player.loop === false}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
            Off
          </button>
          <button
            class="opt"
            class:current={player.loop === true}
            aria-pressed={player.loop === true}
            onclick={() => { player.setLoop(true); close(); }}
          >
            <span class="mark">{#if player.loop === true}<Icon name="check" size={16} />{:else}<span class="spacer"></span>{/if}</span>
            On
          </button>
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
    width: 220px;
    max-width: calc(100vw - 24px);
    max-height: 60vh;
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

  .body {
    display: flex;
    flex-direction: column;
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
</style>
