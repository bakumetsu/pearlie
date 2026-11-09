<script lang="ts">
  import Icon, { type IconName } from "../components/Icon.svelte";
  import type { Mode, Fit } from "./pages";

  let {
    fit,
    mode,
    fullscreen,
    settingsOpen,
    zoom,
    hidden,
    onback,
    onsettings,
    onfit,
    onmode,
    onfullscreen,
    onhelp,
    onzoomin,
    onzoomout,
    onzoomreset,
  }: {
    fit: Fit;
    mode: Mode;
    fullscreen: boolean;
    settingsOpen: boolean;
    zoom: number;
    hidden: boolean;
    onback: () => void;
    onsettings: () => void;
    onfit: () => void;
    onmode: () => void;
    onfullscreen: () => void;
    onhelp: () => void;
    onzoomin: () => void;
    onzoomout: () => void;
    onzoomreset: () => void;
  } = $props();

  let zoomOpen = $state(false);
  $effect(() => {
    if (hidden) zoomOpen = false;
  });
</script>

<nav class="rail" data-testid="rail">
  <button class="btn" aria-label="Back" title="Back" onclick={onback}>
    <Icon name="arrow-left" size={20} />
  </button>
  <button
    class="btn"
    aria-label="Settings"
    title="Settings (s)"
    aria-pressed={settingsOpen}
    onclick={onsettings}
  >
    <Icon name="settings" size={20} />
  </button>
  <button
    class="btn"
    aria-label={"Fit: " + fit}
    title="Fit (f)"
    onclick={onfit}
  >
    <Icon name={`fit-${fit}` as IconName} size={20} />
  </button>
  <button class="btn" aria-label="Zoom" title="Zoom" aria-expanded={zoomOpen} aria-controls="rail-zoom" onclick={() => (zoomOpen = !zoomOpen)}><Icon name="search" size={20} /></button>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div id="rail-zoom" class="zoom" class:open={zoomOpen} inert={!zoomOpen} data-testid="rail-zoom" onkeydown={(e) => { if (e.key === "Escape" && zoomOpen) { e.stopPropagation(); zoomOpen = false; } }}>
    <div class="zoom-inner">
      <button class="btn" aria-label="Zoom in" disabled={zoom >= 300} onclick={onzoomin}><Icon name="plus" size={20} /></button>
      <button class="btn label" aria-label="Reset zoom" onclick={onzoomreset}>{zoom}&thinsp;%</button>
      <button class="btn" aria-label="Zoom out" disabled={zoom <= 50} onclick={onzoomout}><Icon name="minus" size={20} /></button>
    </div>
  </div>
  <button
    class="btn"
    aria-label={"Mode: " + mode}
    title="Mode (m)"
    onclick={onmode}
  >
    <Icon name={`mode-${mode}` as IconName} size={20} />
  </button>
  <button
    class="btn"
    aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}
    title="Fullscreen"
    onclick={onfullscreen}
  >
    <Icon name={fullscreen ? "minimize" : "maximize"} size={20} />
  </button>
  <button class="btn" aria-label="Keys" title="Keys (?)" onclick={onhelp}>
    <Icon name="help" size={20} />
  </button>
</nav>

<style>
  .rail {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    padding: 4px;
    gap: 2px;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    border-radius: var(--r-lg, 12px);
    z-index: 20;
    font-size: var(--t-13, 13px);
  }

  .btn {
    font: inherit;
    color: inherit;
    min-height: 44px;
    min-width: 44px;
    cursor: pointer;
    background: none;
    border: 0;
    border-radius: var(--r-md, 10px);
    padding: 0 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .btn:hover {
    background: var(--line, #26262b);
  }

  .btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .btn:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .btn:disabled:hover {
    background: none;
  }

  .zoom {
    display: grid;
    grid-template-rows: 0fr;
    opacity: 0;
    transition: grid-template-rows 140ms ease-out, opacity 140ms ease-out;
  }

  .zoom.open {
    grid-template-rows: 1fr;
    opacity: 1;
  }

  .zoom-inner {
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-height: 0;
  }

  .label {
    font-size: var(--t-13, 13px);
    font-variant-numeric: tabular-nums;
    color: var(--muted);
  }

  @media (prefers-reduced-motion: reduce) {
    .zoom {
      transition: none;
    }
  }
</style>
