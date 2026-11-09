<script lang="ts">
  import { sfw } from "../stores/sfw.svelte";
  import Icon from "./Icon.svelte";

  const on = $derived(sfw?.on ?? false);
</script>

<button
  type="button"
  class="sfw-toggle"
  aria-label="Hide media (SFW mode)"
  aria-pressed={on}
  title={on ? "Show media (SFW off)" : "Hide media (SFW mode)"}
  onclick={() => sfw?.toggle()}
>
  <Icon name={on ? "eye-off" : "eye"} size={22} />
</button>

<style>
  .sfw-toggle {
    position: fixed;
    top: 8px;
    right: 8px;
    z-index: 1000;
    width: 44px;
    height: 44px;
    display: grid;
    place-items: center;
    border-radius: 999px;
    border: 1px solid var(--line-strong);
    background: rgb(20 20 24 / 0.82);
    backdrop-filter: blur(8px);
    cursor: pointer;
  }
  .sfw-toggle[aria-pressed="true"] {
    background: var(--accent-bg);
    color: var(--accent);
    border-color: var(--accent);
  }
  .sfw-toggle:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
