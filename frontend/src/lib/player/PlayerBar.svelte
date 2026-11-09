<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import { player, RATES } from "./player.svelte";
  import { formatTime } from "./geometry";
  import { pipSupported, isPipActive, enterPip, exitPip, type PipVideo } from "./pip";
  import { onMount } from "svelte";

  let { compact = false }: { compact?: boolean } = $props();

  let video: HTMLVideoElement | null = $state(null);

  onMount(() => {
    video = document.querySelector<HTMLVideoElement>("video[data-player]");
  });

  const pipOk = $derived(video !== null && pipSupported(document, video as PipVideo));

  function onPipClick(): void {
    const v = document.querySelector<HTMLVideoElement>("video[data-player]");
    if (!v) return;
    if (isPipActive(document, v as PipVideo)) {
      exitPip(document, v as PipVideo);
    } else {
      void enterPip(document, v as PipVideo);
    }
  }

  function onFullscreenClick(): void {
    const v = document.querySelector<HTMLVideoElement>("video[data-player]");
    v?.requestFullscreen?.();
  }

  function onRateClick(): void {
    const i = (RATES as readonly number[]).indexOf(player.rate);
    if (i === RATES.length - 1) {
      player.setRate(RATES[0]);
    } else {
      player.stepRate(1);
    }
  }
</script>

<div class="bar" role="group" aria-label="Player controls">
  {#if player.canPrev || player.canNext}
    <button class="btn" aria-label="Previous video" disabled={!player.canPrev} onclick={() => player.prev()}>
      <Icon name="skip-back" size={20} />
    </button>
  {/if}
  {#if !compact}
    <button class="btn" aria-label="Back 10 seconds" onclick={() => player.skip(-10)}>
      <Icon name="rewind" size={20} />
    </button>
  {/if}
  <button
    class="btn"
    aria-label={player.playing ? "Pause" : "Play"}
    onclick={() => player.toggle()}
  >
    <Icon name={player.playing ? "pause" : "play"} size={20} />
  </button>
  {#if !compact}
    <button class="btn" aria-label="Forward 10 seconds" onclick={() => player.skip(10)}>
      <Icon name="fast-forward" size={20} />
    </button>
  {/if}
  {#if player.canPrev || player.canNext}
    <button class="btn" aria-label="Next video" disabled={!player.canNext} onclick={() => player.next()}>
      <Icon name="skip-forward" size={20} />
    </button>
  {/if}

  <input
    class="seek"
    type="range"
    min={0}
    max={player.duration || 0}
    step={0.1}
    value={player.time}
    aria-label="Seek"
    oninput={(e) => player.seek(Number((e.target as HTMLInputElement).value))}
  />

  <span class="time">{formatTime(player.time)} / {formatTime(player.duration)}</span>

  {#if !compact}
    <button class="btn rate" aria-label="Playback speed" onclick={onRateClick}>{player.rate}x</button>
  {/if}

  <button
    class="btn"
    aria-label={player.muted ? "Unmute" : "Mute"}
    onclick={() => player.toggleMute()}
  >
    <Icon name={player.muted ? "volume-x" : "volume"} size={20} />
  </button>

  {#if !compact}
    <input
      class="vol"
      type="range"
      min={0}
      max={1}
      step={0.05}
      value={player.volume}
      aria-label="Volume"
      oninput={(e) => player.setVolume(Number((e.target as HTMLInputElement).value))}
    />
  {/if}

  {#if pipOk}
    <button class="btn" aria-label="Picture in picture" onclick={onPipClick}>
      <Icon name="pip" size={20} />
    </button>
  {/if}

  <button class="btn" aria-label="Fullscreen" onclick={onFullscreenClick}>
    <Icon name="maximize" size={20} />
  </button>
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: var(--s-1);
    padding: var(--s-1) var(--s-2);
    background: var(--surface);
    border-top: 1px solid var(--line);
    border-radius: var(--r-sm);
    width: 100%;
    box-sizing: border-box;
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

  .seek {
    flex: 1;
    min-width: 60px;
    accent-color: var(--accent);
  }

  .vol {
    width: 64px;
    accent-color: var(--accent);
  }

  .time {
    font-size: var(--t-12);
    color: var(--muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .rate {
    font-size: var(--t-12);
    font-variant-numeric: tabular-nums;
  }
</style>
