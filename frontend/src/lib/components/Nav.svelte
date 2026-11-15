<script lang="ts">
  import Icon from "./Icon.svelte";
  import { rail } from "../stores/rail.svelte";

  interface Props {
    current: string;
    queueBadge?: number;
    onnavigate: (e: MouseEvent) => void;
    variant?: "rail" | "bar";
  }

  let { current, queueBadge, onnavigate, variant = "rail" }: Props = $props();

  const items = [
    { name: "discover", label: "Discover", icon: "search", path: "/" },
    { name: "home", label: "Home", icon: "home", path: "/home" },
    { name: "library", label: "Library", icon: "library", path: "/library" },
    { name: "queue", label: "Queue", icon: "queue", path: "/queue" },
    { name: "trash", label: "Trash", icon: "trash", path: "/trash" },
    { name: "options", label: "Options", icon: "wrench", path: "/options" },
  ] as const;

  let dragging = $state(false);

  function startDrag(e: PointerEvent): void {
    if (!rail || e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
  }

  function moveDrag(e: PointerEvent): void {
    if (dragging) rail?.setWidth(e.clientX);
  }

  function endDrag(): void {
    dragging = false;
  }

  function keyResize(e: KeyboardEvent): void {
    if (!rail) return;
    const step = e.shiftKey ? 32 : 8;
    if (e.key === "ArrowLeft") rail.setWidth(rail.width - step);
    else if (e.key === "ArrowRight") rail.setWidth(rail.width + step);
    else if (e.key === "Enter" || e.key === "Home") rail.resetWidth();
    else return;
    e.preventDefault();
  }

  function isActive(name: string): boolean {
    if (name === "library") {
      return current === "library" || current.startsWith("library_");
    }
    return current === name;
  }
</script>

<nav class="nav {variant}" class:dragging aria-label="Main">
  {#each items as item (item.name)}
    <a
      href={item.path}
      class="nav-item {isActive(item.name) ? "active" : ""}"
      aria-current={isActive(item.name) ? "page" : undefined}
      onclick={onnavigate}
    >
      <Icon name={item.icon} size={20} />
      <span class="nav-label">{item.label}</span>
      {#if item.name === "queue" && queueBadge && queueBadge > 0}
        <span class="nav-badge">{queueBadge}</span>
      {/if}
    </a>
  {/each}
  {#if variant === "rail" && rail}
    <button
      type="button"
      class="rail-toggle"
      aria-label="Hide navigation"
      title="Hide navigation"
      onclick={() => rail?.toggle()}
    >
      <Icon name="chevrons-left" size={20} />
    </button>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div
      class="rail-resize"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize navigation (double-click to reset)"
      aria-valuemin={72}
      aria-valuemax={240}
      aria-valuenow={rail.width}
      tabindex="0"
      onpointerdown={startDrag}
      onpointermove={moveDrag}
      onpointerup={endDrag}
      onpointercancel={endDrag}
      ondblclick={() => rail?.resetWidth()}
      onkeydown={keyResize}
    ></div>
  {/if}
</nav>
{#if variant === "rail" && rail?.collapsed}
  <button
    type="button"
    class="rail-reopen"
    aria-label="Show navigation"
    title="Show navigation"
    onclick={() => rail?.toggle()}
  >
    <Icon name="chevrons-right" size={20} />
  </button>
{/if}

<style>
  .nav {
    display: flex;
  }

  /* --- rail variant --- */
  .nav.rail {
    position: fixed;
    top: 0;
    left: 0;
    width: var(--rail-w);
    height: 100dvh;
    flex-direction: column;
    align-items: stretch;
    background: var(--rail);
    z-index: 900;
    overflow-x: hidden;
    transition: width 250ms ease, transform 250ms ease;
  }

  .nav.rail .nav-item {
    height: 56px;
    min-height: 56px;
    width: 100%;
    flex-direction: column;
    gap: var(--s-1);
    padding: var(--s-2) 0;
  }

  .rail-toggle {
    margin-top: auto;
    flex: none;
    width: 100%;
    height: 44px;
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 0;
    color: var(--muted);
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }

  .rail-toggle:hover {
    color: var(--text);
    background: var(--surface);
  }

  /* Short screens (landscape phone) slim icons, no labels. Short screens scroll if it still does not fit. */
  @media (max-height: 500px) {
    .nav.rail {
      overflow-y: auto;
      scrollbar-width: none;
    }

    .nav.rail .nav-item {
      height: 44px;
      min-height: 44px;
      padding: 0;
    }

    .nav.rail .nav-label {
      display: none;
    }
  }

  /* Hidden rail: off screen and out of the tab order; the re-open button takes over. */
  :global(:root[data-rail="hidden"]) .nav.rail {
    transform: translateX(-100%);
    visibility: hidden;
  }

  /* Bottom-left chevron, shown while the pointer is over its corner zone (always on touch). */
  .rail-reopen {
    position: fixed;
    bottom: var(--s-2);
    left: var(--s-2);
    width: 44px;
    height: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--rail);
    border: 0;
    border-radius: 50%;
    color: var(--muted);
    cursor: pointer;
    z-index: 900;
    opacity: 0;
    transition: opacity 0.15s, background 0.15s, color 0.15s;
  }

  .rail-reopen::before {
    content: "";
    position: absolute;
    inset: -8px -16px -8px -16px;
  }

  .rail-reopen:hover,
  .rail-reopen:focus-visible {
    opacity: 1;
  }

  @media (hover: none) {
    .rail-reopen {
      opacity: 1;
    }
  }

  .rail-reopen:hover {
    color: var(--text);
    background: var(--surface);
  }

  @media (prefers-reduced-motion: reduce) {
    .nav.rail {
      transition: none;
    }
  }

  /* --- bar variant --- */
  .nav.bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    flex-direction: row;
    justify-content: space-evenly;
    align-items: center;
    background: var(--rail);
    border-top: 1px solid var(--line);
    z-index: 900;
  }

  .nav.bar .nav-item {
    width: 56px;
    height: 48px;
    flex-direction: column;
    gap: var(--s-1);
    padding: var(--s-1) 0;
  }

  /* --- shared item styles --- */
  .nav-item {
    position: relative;
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    color: var(--muted);
    border-radius: var(--r-md);
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }

  .nav-item:hover {
    color: var(--text);
    background: var(--surface);
  }

  .nav-item.active {
    color: var(--accent);
    background: var(--accent-bg);
  }

  .nav-label {
    font-size: 11px;
    line-height: 1;
  }

  .nav-badge {
    position: absolute;
    top: 4px;
    right: 4px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: var(--r-lg);
    background: var(--accent);
    color: var(--bg);
    font-size: 10px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }
</style>
