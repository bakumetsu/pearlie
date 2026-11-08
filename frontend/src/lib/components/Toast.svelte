<script lang="ts">
  import Icon from "./Icon.svelte";
  import { toasts } from "../stores/toasts.svelte";
</script>

<div
  class="toast-region"
  role="status"
  aria-live="polite"
  onmouseenter={() => toasts.pause()}
  onfocusin={() => toasts.pause()}
  onmouseleave={() => toasts.resume()}
  onfocusout={() => toasts.resume()}
>
  {#if toasts.current}
    {@const toast = toasts.current}
    <div class="toast {toast.kind}">
      {#if toast.kind === "error"}
        <Icon name="alert" size={16} />
      {/if}
      <span class="toast-msg">{toast.message}</span>
      {#if toast.actionLabel}
        {#if toast.href}
          <a class="toast-action" href={toast.href} onclick={() => toasts.runAction()}>
            {toast.actionLabel}
          </a>
        {:else}
          <button class="toast-action" onclick={() => toasts.runAction()}>
            {toast.actionLabel}
          </button>
        {/if}
      {/if}
      <button class="toast-close" aria-label="Dismiss" onclick={() => toasts.dismiss()}>
        <Icon name="x" size={16} />
      </button>
    </div>
  {/if}
</div>

<style>
  .toast-region {
    position: fixed;
    left: calc(var(--rail-w) + 16px);
    bottom: calc(16px + var(--player-bottom-offset));
    z-index: 1000;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    padding: var(--s-3);
    border-radius: var(--r-md);
    background: var(--surface);
    border: 1px solid var(--line-strong);
    color: var(--text);
    font-size: var(--t-14);
    box-shadow: 0 4px 12px rgb(0 0 0 / 0.15);
  }

  .toast.error {
    background: var(--danger-bg);
    color: var(--danger-fg);
    border-color: var(--danger-fg);
  }

  .toast-msg {
    flex: 1;
  }

  .toast-action {
    min-height: 44px;
    min-width: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 var(--s-3);
    border-radius: var(--r-sm);
    background: none;
    border: none;
    color: var(--accent);
    font-size: var(--t-14);
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
  }

  .toast-action:hover {
    text-decoration: underline;
  }

  .toast-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
    border-radius: var(--r-sm);
  }

  .toast-close:hover {
    background: var(--accent-bg);
  }
</style>
