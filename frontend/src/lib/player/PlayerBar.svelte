<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import GearMenu from "./GearMenu.svelte";
  import { player } from "./player.svelte";
  import { formatTime } from "./geometry";
  import { pipSupported, isPipActive, enterPip, exitPip, type PipVideo } from "./pip";
  import { onMount } from "svelte";

  let { compact = false, fullscreen = false }: { compact?: boolean; fullscreen?: boolean } = $props();

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
    if (fullscreen) {
      const exit =
        document.exitFullscreen ??
        (document as { webkitExitFullscreen?: () => Promise<void> }).webkitExitFullscreen;
      const p = exit?.call(document);
      if (p) void p.catch(() => {});
      return;
    }
    const root = document.querySelector<HTMLElement>("[data-player-root]");
    if (root) {
      const webkit = (root as { webkitRequestFullscreen?: () => Promise<void> }).webkitRequestFullscreen;
      if (typeof root.requestFullscreen === "function" || typeof webkit === "function") {
        const p = typeof root.requestFullscreen === "function" ? root.requestFullscreen() : webkit?.call(root);
        if (p) void p.catch(() => {});
        return;
      }
    }
    const v = document.querySelector<HTMLVideoElement>("video[data-player]");
    if (!v) return;
    const pv =
      v.requestFullscreen?.() ??
      (v as { webkitEnterFullscreen?: () => Promise<void> }).webkitEnterFullscreen?.();
    if (pv) void pv.catch(() => {});
  }

</script>

<div class="bar" role="group" aria-label="Player controls">
  <button class="btn" aria-label="Previous video" disabled={!player.canPrev} onclick={() => player.prev()}>
    <Icon name="rewind" size={20} />
  </button>
  <button
    class="btn"
    aria-label={player.playing ? "Pause" : "Play"}
    onclick={() => player.toggle()}
  >
    <Icon name={player.playing ? "pause" : "play"} size={20} />
  </button>
  <button class="btn" aria-label="Next video" disabled={!player.canNext} onclick={() => player.next()}>
    <Icon name="fast-forward" size={20} />
  </button>

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

  {#if !compact}
    <GearMenu />
  {/if}

  <button class="btn" aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"} onclick={onFullscreenClick}>
    <Icon name={fullscreen ? "minimize" : "maximize"} size={20} />
  </button>
</div>

<style>
  .bar {
    position: relative;
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

</style>
