<script lang="ts">
  import Icon from "../components/Icon.svelte";

  interface Props {
    onclose: () => void;
  }

  let { onclose }: Props = $props();

  const keys = [
    ["← / →", "Turn page (follows direction)"],
    ["Space / Shift+Space", "Next / previous page"],
    ["PageDown / PageUp", "Next / previous page"],
    ["Home / End", "First / last page"],
    ["[ / ]", "Previous / next book"],
    ["b", "Book list"],
    ["s", "View settings"],
    ["f", "Step fit"],
    ["m", "Step mode"],
    ["1 2 3", "Single / spread / scroll"],
    ["Shift+F", "Fullscreen"],
    ["t", "Thumbnails"],
    ["- + 0", "Zoom out / in / reset"],
    ["h", "Hide or show controls"],
    ["r", "Reading direction"],
    ["?", "This help"],
    ["Esc", "Close / leave"],
  ] as const;

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onclose();
    }
  }

  $effect(() => {
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  });
</script>

<div class="backdrop" role="presentation" onclick={() => onclose()}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="sheet" role="dialog" tabindex="-1" aria-label="Keyboard shortcuts" aria-modal="true" onclick={(e) => e.stopPropagation()}>
    <div class="header">
      <h3>Keyboard shortcuts</h3>
      <button aria-label="Close" onclick={() => onclose()}>
        <Icon name="x" size={20} />
      </button>
    </div>
    <table>
      <tbody>
        {#each keys as [key, desc] (key)}
          <tr>
            <td class="key">{key}</td>
            <td class="desc">{desc}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 70;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.5);
  }

  .sheet {
    background: rgb(20 20 24 / 0.82);
    border: 1px solid var(--line-strong);
    backdrop-filter: blur(8px);
    border-radius: var(--r-lg, 12px);
    padding: 20px 24px;
    width: min(460px, 92vw);
    color: var(--t-13, var(--muted));
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .header h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--text, #ECECEF);
  }

  button {
    min-width: 44px;
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    border-radius: var(--r-md, 10px);
    cursor: pointer;
    color: var(--text, #ECECEF);
    padding: 0;
  }

  button:hover {
    background: var(--line, #26262B);
  }

  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  td {
    padding: 4px 0;
    vertical-align: top;
    font-size: var(--t-13, 13px);
  }

  .key {
    font-family: ui-monospace, Consolas, monospace;
    color: var(--accent, #7FB0FF);
    white-space: nowrap;
    padding-right: 16px;
  }

  .desc {
    color: var(--t-13, var(--muted));
  }
</style>
