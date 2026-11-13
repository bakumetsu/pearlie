<script lang="ts">
  import { hostBlock } from "../stores/hostBlock.svelte";
</script>

{#if hostBlock.message}
  <div class="host-block" role="alert">
    <h1>Pearlie cannot be used from this address</h1>
    <p>{hostBlock.message}</p>
    <p class="hint">Set it in <code>.env</code> next to the Pearlie backend, then restart Pearlie.</p>
  </div>
{/if}

<style>
  .host-block {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 24px;
    text-align: center;
    background: var(--bg, #111);
    color: var(--fg, #eee);
  }
  h1 {
    font-size: 1.25rem;
    margin: 0;
  }
  p {
    margin: 0;
    max-width: 36rem;
    overflow-wrap: anywhere;
  }
  .hint {
    opacity: 0.7;
  }
</style>
