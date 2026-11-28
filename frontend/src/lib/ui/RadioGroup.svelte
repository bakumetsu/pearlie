<script lang="ts">
  import { cn } from "$lib/utils";

  type Option = { value: string; label: string };
  let {
    value = $bindable(""),
    options,
    label,
    class: className = "",
  }: { value?: string; options: Option[]; label: string; class?: string } = $props();

  // Roving tabindex: arrows move and select, as native radios do.
  function onkeydown(e: KeyboardEvent, i: number) {
    const step = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = options[(i + step + options.length) % options.length];
    value = next.value;
    const radios = (e.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLElement>("[data-v]");
    Array.from(radios ?? []).find((r) => r.dataset.v === next.value)?.focus();
  }
</script>

<div role="radiogroup" aria-label={label} class={cn("flex flex-col gap-0.5", className)}>
  {#each options as o, i (o.value)}
    <button
      type="button"
      role="radio"
      data-v={o.value}
      aria-checked={value === o.value}
      tabindex={value === o.value || (!value && i === 0) ? 0 : -1}
      onclick={() => (value = o.value)}
      onkeydown={(e) => onkeydown(e, i)}
      class="flex h-11 items-center gap-2.5 rounded-md px-2.5 text-left hover:bg-border focus-visible:outline-2 focus-visible:outline-ring"
    >
      <span class="grid size-5 place-items-center rounded-full border border-input {value === o.value ? 'border-primary' : ''}">
        {#if value === o.value}<span class="size-2.5 rounded-full bg-primary"></span>{/if}
      </span>
      {o.label}
    </button>
  {/each}
</div>
