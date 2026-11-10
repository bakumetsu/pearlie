<script lang="ts">
  import { player } from "./player.svelte";
  import { rectFor, toTransform } from "./geometry";
  import { setMediaSession, enterPip } from "./pip";
  import PlayerBar from "./PlayerBar.svelte";

  let video: HTMLVideoElement | null = null;

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
      player.reapplyRate();
      if (player.consumeAutoplay()) {
        const p = video.play();
        if (p && typeof p.catch === "function") p.catch(() => {});
      }
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

<div data-sfw-group style="display:contents">
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

  {#if player.mode === "stage" && player.slot !== null && player.item !== null && rect !== null}
    <div
      class="stage-bar"
      style="position:fixed;left:{rect.x}px;width:{rect.w}px;top:{rect.y + rect.h - 52}px;z-index:21;"
    >
      <PlayerBar />
    </div>
  {/if}
</div>

<style>
  .stage-bar {
    box-sizing: border-box;
  }
</style>
