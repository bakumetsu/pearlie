<script lang="ts">
  import { untrack } from "svelte";
  import { player } from "./player.svelte";
  import { rectFor, toTransform } from "./geometry";
  import { setMediaSession, enterPip } from "./pip";
  import PlayerBar from "./PlayerBar.svelte";

  let video: HTMLVideoElement | null = null;
  let root: HTMLDivElement | null = null;
  let fs = $state(false);

  let vp = $state({ w: window.innerWidth, h: window.innerHeight });

  $effect(() => {
    const onResize = () => {
      vp.w = window.innerWidth;
      vp.h = window.innerHeight;
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  });

  $effect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (player.item === null) return;
      if (player.mode !== "stage" && player.mode !== "mini") return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable)
      )
        return;
      switch (e.key) {
        case "j":
        case "J":
          e.preventDefault();
          player.skip(-10);
          break;
        case "l":
        case "L":
          e.preventDefault();
          player.skip(10);
          break;
        case "<":
          e.preventDefault();
          player.stepRate(-1);
          break;
        case ">":
          e.preventDefault();
          player.stepRate(1);
          break;
        case "N":
          if (e.shiftKey) {
            e.preventDefault();
            player.next();
          }
          break;
        case "P":
          if (e.shiftKey) {
            e.preventDefault();
            player.prev();
          }
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const rect = $derived(rectFor(player.mode, player.slot, vp));

  // Mini dock is z-index 21 with an opaque background, so the mini video must sit above it.
  const videoStyle = $derived(
    rect === null
      ? "position:fixed;top:0;left:0;z-index:20;background:#000;object-fit:contain;display:none;"
      : `position:fixed;top:0;left:0;z-index:${player.mode === "mini" ? 22 : 20};background:#000;object-fit:contain;width:${rect.w}px;height:${rect.h}px;transform:${toTransform(rect)};`,
  );

  $effect(() => {
    player.attach(video);
    return () => player.attach(null);
  });

  $effect(() => {
    const item = player.item;
    setMediaSession(
      navigator,
      item ? { title: item.title, poster: item.posterUrl } : null,
      {
        play: () => player.play(),
        pause: () => player.pause(),
        enterPip: () => {
          if (video) void enterPip(document, video as Parameters<typeof enterPip>[1]);
        },
      },
    );
  });

  $effect(() => {
    const item = player.item;
    if (item !== null && video !== null) {
      video.load();
      untrack(() => player.reapplyRate());
      if (player.consumePlayOnLoad()) {
        const p = video.play();
        if (p && typeof p.catch === "function") p.catch(() => {});
      }
    }
  });

  function fsElement(): Element | null {
    return (
      document.fullscreenElement ??
      (document as { webkitFullscreenElement?: Element }).webkitFullscreenElement ??
      null
    );
  }

  $effect(() => {
    const sync = () => {
      fs = root !== null && fsElement() === root;
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      document.removeEventListener("webkitfullscreenchange", sync);
      if (fsElement() === root) {
        const p = (
          document.exitFullscreen ??
          (document as { webkitExitFullscreen?: () => Promise<void> }).webkitExitFullscreen
        )?.call(document);
        if (p) void p.catch(() => {});
      }
    };
  });

  $effect(() => {
    const item = player.item;
    if (item === null && untrack(() => fs)) {
      const p = (
        document.exitFullscreen ??
        (document as { webkitExitFullscreen?: () => Promise<void> }).webkitExitFullscreen
      )?.call(document);
      if (p) void p.catch(() => {});
    }
  });

  function onVideoClick(): void {
    if (player.mode === "stage") player.toggle();
  }

  function onVideoError(): void {
    const url = player.onSourceError();
    if (url !== null) player.playSource(url, false);
  }
</script>

<div data-sfw-group data-player-root class="root" bind:this={root}>
  <!-- svelte-ignore a11y_media_has_caption -->
  <video
    data-player
    bind:this={video}
    playsinline
    preload="metadata"
    src={player.item?.streamUrl}
    poster={player.item?.posterUrl}
    style={videoStyle}
    ontimeupdate={() => {
      if (video) player.onTime(video.currentTime, video.duration);
    }}
    onloadedmetadata={() => {
      if (video) player.onTime(video.currentTime, video.duration);
    }}
    onplaying={() => player.onPlaying()}
    onpause={() => player.onPause()}
    onended={() => player.onEnded()}
    onclick={onVideoClick}
    onerror={onVideoError}
  ></video>

  {#if player.item !== null && (fs || (player.mode === "stage" && player.slot !== null && rect !== null))}
    <div
      class="stage-bar"
      style={rect !== null ? `position:fixed;left:${rect.x}px;width:${rect.w}px;bottom:${vp.h - rect.y - rect.h}px;z-index:21;` : ""}
    >
      <PlayerBar fullscreen={fs} />
    </div>
  {/if}
</div>

<style>
  .root {
    display: contents;
  }

  .root:fullscreen {
    display: flex;
    flex-direction: column;
    background: #000;
    width: 100%;
    height: 100%;
  }

  .root:-webkit-full-screen {
    display: flex;
    flex-direction: column;
    background: #000;
    width: 100%;
    height: 100%;
  }

  .root:fullscreen > :global(video) {
    position: static !important;
    transform: none !important;
    flex: 1 1 auto;
    min-height: 0;
    width: 100% !important;
    height: auto !important;
    object-fit: contain;
    display: block !important;
  }

  .root:-webkit-full-screen > :global(video) {
    position: static !important;
    transform: none !important;
    flex: 1 1 auto;
    min-height: 0;
    width: 100% !important;
    height: auto !important;
    object-fit: contain;
    display: block !important;
  }

  .root:fullscreen .stage-bar {
    position: static !important;
    width: 100% !important;
    flex: 0 0 auto;
    z-index: auto !important;
  }

  .root:-webkit-full-screen .stage-bar {
    position: static !important;
    width: 100% !important;
    flex: 0 0 auto;
    z-index: auto !important;
  }

  .stage-bar {
    box-sizing: border-box;
  }
</style>
