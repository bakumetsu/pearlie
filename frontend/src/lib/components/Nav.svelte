<script lang="ts">
  import Icon from "./Icon.svelte";

  interface Props {
    current: string;
    queueBadge?: number;
    onnavigate: (e: MouseEvent) => void;
    variant?: "rail" | "bar";
  }

  let { current, queueBadge, onnavigate, variant = "rail" }: Props = $props();

  const items = [
    { name: "discover", label: "Discover", icon: "search", path: "/" },
    { name: "library", label: "Library", icon: "library", path: "/library" },
    { name: "queue", label: "Queue", icon: "queue", path: "/queue" },
    { name: "rules", label: "Rules", icon: "rules", path: "/rules" },
    { name: "trash", label: "Trash", icon: "trash", path: "/trash" },
  ] as const;

  function isActive(name: string): boolean {
    if (name === "library") {
      return current === "library" || current.startsWith("library_");
    }
    return current === name;
  }
</script>

<nav class="nav {variant}" aria-label="Main">
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
</nav>

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
    border-right: 1px solid var(--line);
    z-index: 900;
  }

  .nav.rail .nav-item {
    height: 56px;
    min-height: 56px;
    width: 100%;
    flex-direction: column;
    gap: var(--s-1);
    padding: var(--s-2) 0;
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
