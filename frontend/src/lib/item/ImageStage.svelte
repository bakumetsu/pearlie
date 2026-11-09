<script lang="ts">
  let { src, alt, preload = null, zoomed = $bindable(false) }: {
    src: string;
    alt: string;
    preload?: string | null;
    zoomed?: boolean;
  } = $props();
</script>

<svelte:head>
  {#if preload}
    <link rel="preload" as="image" href={preload} />
  {/if}
</svelte:head>

<div class="stage" class:zoomed={zoomed}>
  <button
    type="button"
    class="imgbtn"
    aria-label={zoomed ? "Fit to screen" : "Actual size"}
    onclick={() => (zoomed = !zoomed)}
  >
    <img {src} {alt} class:zoomed={zoomed} />
  </button>
</div>

<style>
  .stage {
    position: relative;
    width: 100%;
    height: 100%;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .stage.zoomed {
    overflow: auto;
  }
  .imgbtn {
    min-width: 0;
    min-height: 0;
    padding: 0;
    border: 0;
    background: none;
    cursor: zoom-in;
    display: block;
  }
  .stage.zoomed .imgbtn {
    cursor: zoom-out;
  }
  .stage:not(.zoomed) .imgbtn {
    max-width: 100%;
    max-height: 100%;
  }
  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
  }
  img.zoomed {
    max-width: none;
    max-height: none;
  }
</style>
