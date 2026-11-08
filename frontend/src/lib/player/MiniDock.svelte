<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import { player } from "./player.svelte";
  import { formatTime } from "./geometry";
  import { pipSupported, isPipActive, enterPip, exitPip, type PipVideo } from "./pip";
  import { getRouter } from "../ctx";
  import { linkClick } from "../router";

  let pipOk = $state(false);

  $effect(() => {
    const v = document.querySelector<HTMLVideoElement>("video[data-player]");
    if (v) pipOk = pipSupported(document, v as PipVideo);
  });

  const pct = $derived(player.duration > 0 ? (player.time / player.duration) * 100 : 0);

  function onPipClick(): void {
    const v = document.querySelector<HTMLVideoElement>("video[data-player]");
    if (!v) return;
    if (isPipActive(document, v as PipVideo)) {
      exitPip(document, v as PipVideo);
    } else {
      void enterPip(document, v as PipVideo);
    }
  }

  function onKeydown(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (t.tagName === "INPUT" || t.tagName === "BUTTON") return;
    if (e.key === " ") {
      e.preventDefault();
      player.toggle();
    }
  }
</script>

{#if player.mode === "mini" && player.item !== null}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <section class="dock" aria-label="Mini player" onkeydown={onKeydown}>
    <div class="spacer"></div>

    <a
      class="title"
      href={player.item.href}
      onclick={(e: MouseEvent) => linkClick(e, getRouter())}
    >
      {player.item.title}
    </a>

    <span class="time">{formatTime(player.time)} / {formatTime(player.duration)}</span>

    <button
      class="btn"
      aria-label={player.playing ? "Pause" : "Play"}
      onclick={() => player.toggle()}
    >
      <Icon name={player.playing ? "pause" : "play"} size={20} />
    </button>

    {#if pipOk}
      <button class="btn" aria-label="Picture in picture" onclick={onPipClick}>
        <Icon name="pip" size={20} />
      </button>
    {/if}

    <button class="btn" aria-label="Close player" onclick={() => player.close()}>
      <Icon name="x" size={20} />
    </button>

    <div class="progress" style="width: {pct}%"></div>
  </section>
{/if}

<style>
  .dock {
    position: fixed;
    left: var(--rail-w);
    right: 0;
    bottom: 0;
    height: 72px;
    z-index: 21;
    background: var(--surface);
    border-top: 1px solid var(--line);
    display: flex;
    align-items: center;
    gap: var(--s-1);
    padding: 0 var(--s-2);
    box-sizing: border-box;
    overflow: hidden;
  }

  .spacer {
    width: 120px;
    flex-shrink: 0;
  }

  .title {
    font-size: var(--t-12);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text);
    text-decoration: none;
    flex: 1;
    min-width: 0;
  }

  .time {
    font-size: var(--t-12);
    color: var(--muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
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
    flex-shrink: 0;
  }

  .btn:hover {
    background: var(--line);
  }

  .progress {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 3px;
    background: var(--accent);
    transition: width 0.2s linear;
  }
</style>
