<script lang="ts">
  import Icon from "../components/Icon.svelte";
  import type { Mode, Fit } from "./pages";

  let {
    fit,
    mode,
    fullscreen,
    settingsOpen,
    onback,
    onsettings,
    onfit,
    onmode,
    onfullscreen,
    onhelp,
  }: {
    fit: Fit;
    mode: Mode;
    fullscreen: boolean;
    settingsOpen: boolean;
    onback: () => void;
    onsettings: () => void;
    onfit: () => void;
    onmode: () => void;
    onfullscreen: () => void;
    onhelp: () => void;
  } = $props();
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
    <Icon name={"fit-" + fit} size={20} />
  </button>
  <button
    class="btn"
    aria-label={"Mode: " + mode}
    title="Mode (m)"
    onclick={onmode}
  >
    <Icon name={"mode-" + mode} size={20} />
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
</style>
