<script lang="ts">
  import { sfw } from "$lib/stores/sfw.svelte";
  import IconButton from "$lib/ui/IconButton.svelte";

  // Same store and labels as components/SfwToggle.svelte:4-14.
  const on = $derived(sfw?.on ?? false);
</script>

<IconButton
  icon={on ? "eye-off" : "eye"}
  iconSize={22}
  label={on ? "Show media (SFW off)" : "Hide media (SFW mode)"}
  aria-pressed={on}
  class="rounded-pill aria-pressed:bg-accent aria-pressed:text-primary!"
  onclick={() => sfw?.toggle()}
/>
