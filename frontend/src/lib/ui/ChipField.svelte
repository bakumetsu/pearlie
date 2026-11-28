<script lang="ts">
  import type { Chip } from "../query";
  import { chipLabel, chipRemoveLabel, commitText, hasOpenQuote, removeLastChip } from "../query";
  import { cn } from "$lib/utils";

  // Same keys as components/ChipField.svelte: Enter and comma commit, Enter on empty submits, Backspace on empty removes the last chip.
  let {
    chips,
    onchange,
    label = "Search everything",
    onsubmit,
    pending = $bindable(""),
    class: className = "",
  }: { chips: Chip[]; onchange: (chips: Chip[]) => void; label?: string; onsubmit?: () => void; pending?: string; class?: string } = $props();
</script>

<div
  role="group"
  aria-label={label}
  class={cn(
    "flex min-h-11 flex-wrap items-center gap-1 rounded-pill border border-input bg-card px-3 py-1 focus-within:border-primary",
    className,
  )}
>
  {#each chips as chip (chip.raw)}
    <span class={cn("inline-flex items-center gap-1 rounded-pill bg-accent pl-2.5 text-[13px] text-accent-foreground", chip.exclude && "text-destructive")}>
      {chipLabel(chip)}
      <button
        type="button"
        aria-label={chipRemoveLabel(chip)}
        onclick={() => onchange(chips.filter((c) => c.raw !== chip.raw))}
        class="inline-grid size-11 place-items-center rounded-full hover:bg-border focus-visible:outline-2 focus-visible:outline-ring">×</button
      >
    </span>
  {/each}
  <input
    bind:value={pending}
    type="text"
    autocomplete="off"
    aria-label={label}
    placeholder={chips.length === 0 ? 'Search tags or "title", e.g. cat -dog artist:x' : ""}
    class="h-9 min-w-24 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
    onkeydown={(e) => {
      if (e.key === "," && hasOpenQuote(pending)) return;
      if ((e.key === "Enter" || e.key === ",") && pending.trim()) {
        e.preventDefault();
        onchange(commitText(chips, pending));
        pending = "";
      } else if (e.key === "Enter" && !pending.trim()) {
        e.preventDefault();
        onsubmit?.();
      } else if (e.key === "Backspace" && pending === "") {
        onchange(removeLastChip(chips));
      }
    }}
  />
</div>
