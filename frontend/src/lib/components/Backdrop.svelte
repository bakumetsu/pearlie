<script lang="ts">
  let { src, strength }: { src: string | null | undefined; strength: number } = $props();

  function escapeCssUrl(value: string): string {
    return value.replace(/([\\"])/g, "\\$1");
  }

  const fillStyle = $derived(
    src ? `background-image:url("${escapeCssUrl(src)}");opacity:${strength / 100}` : "",
  );
</script>

{#if strength > 0 && src}
  <div class="backdrop" aria-hidden="true" data-testid="backdrop">
    <div class="fill" style={fillStyle}></div>
  </div>
{/if}

<style>
  .backdrop {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
  }

  .fill {
    background-size: cover;
    background-position: center;
    filter: blur(40px) saturate(1.1);
    transform: scale(1.25);
  }
</style>
