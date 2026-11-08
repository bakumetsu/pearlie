<script lang="ts">
  import type { Mode, Fit, Dir } from "./pages";
  import Icon, { type IconName } from "../components/Icon.svelte";

  let {
    mode,
    fit,
    dir,
    onmode,
    onfit,
    ondir,
    onclose,
  }: {
    mode: Mode;
    fit: Fit;
    dir: Dir;
    onmode: (m: Mode) => void;
    onfit: (f: Fit) => void;
    ondir: (d: Dir) => void;
    onclose: () => void;
  } = $props();

  function handleKey(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
  }

  const modeOptions: { value: Mode; label: string; icon: IconName }[] = [
    { value: "single", label: "Single page", icon: "mode-single" },
    { value: "spread", label: "Spread", icon: "mode-spread" },
    { value: "scroll", label: "Scroll", icon: "mode-scroll" },
  ];

  const fitOptions: { value: Fit; label: string; icon: IconName }[] = [
    { value: "width", label: "Fit width", icon: "fit-width" },
    { value: "height", label: "Fit height", icon: "fit-height" },
    { value: "both", label: "Fit both", icon: "fit-both" },
    { value: "actual", label: "1:1", icon: "fit-actual" },
  ];

  const dirOptions: { value: Dir; label: string }[] = [
    { value: "ltr", label: "LTR" },
    { value: "rtl", label: "RTL" },
  ];
</script>

<div role="dialog" aria-label="View" tabindex="-1" class="popover" onkeydown={handleKey}>
  <h4>View</h4>

  <div class="row">
    <span>Mode</span>
    <div class="grp">
      {#each modeOptions as opt (opt.value)}
        <button
          class:on={mode === opt.value}
          aria-pressed={mode === opt.value}
          aria-label={opt.label}
          title={opt.label}
          onclick={() => onmode(opt.value)}
        >
          <Icon name={opt.icon} size={20} />
        </button>
      {/each}
    </div>
  </div>

  <div class="row">
    <span>Fit</span>
    <div class="grp">
      {#each fitOptions as opt (opt.value)}
        <button
          class:on={fit === opt.value}
          aria-pressed={fit === opt.value}
          aria-label={opt.label}
          title={opt.label}
          onclick={() => onfit(opt.value)}
        >
          <Icon name={opt.icon} size={20} />
        </button>
      {/each}
    </div>
  </div>

  <div class="row">
    <span>Direction</span>
    <div class="grp">
      {#each dirOptions as opt (opt.value)}
        <button
          class:on={dir === opt.value}
          aria-pressed={dir === opt.value}
          onclick={() => ondir(opt.value)}
        >
          {opt.label}
        </button>
      {/each}
    </div>
  </div>
</div>

<style>
  .popover {
    position: absolute;
    right: 72px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 30;
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    border-radius: 12px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 280px;
    color: var(--t-13);
    font-size: 13px;
  }

  h4 {
    margin: 0;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .row > span {
    color: var(--muted);
    font-size: 13px;
  }

  .grp {
    display: inline-flex;
    gap: 2px;
    padding: 2px;
    border-radius: 12px;
    background: var(--rail, #17171a);
    border: 1px solid var(--line, #26262b);
  }

  .grp button {
    font: inherit;
    color: inherit;
    min-height: 44px;
    min-width: 44px;
    cursor: pointer;
    background: none;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .grp button.on {
    background: var(--accent-bg, #22324f);
    color: var(--accent, #7fb0ff);
    border-color: var(--accent, #7fb0ff);
  }

  .grp button:hover:not(.on) {
    background: var(--line, #26262b);
  }

  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
