<script lang="ts">
  import type { HTMLButtonAttributes } from "svelte/elements";
  import Icon, { type IconName } from "../components/Icon.svelte";
  import Button from "./Button.svelte";

  // Icon-only buttons always carry a label: aria-label and title (rule 7).
  let {
    icon,
    label,
    iconSize = 20,
    variant = "ghost",
    ...rest
  }: Omit<HTMLButtonAttributes, "title" | "aria-label"> & {
    icon: IconName;
    label: string;
    iconSize?: number;
    variant?: "default" | "outline" | "ghost" | "destructive" | "pill" | "chip";
  } = $props();
</script>

<Button size="icon" {variant} aria-label={label} title={label} {...rest}>
  <Icon name={icon} size={iconSize} />
</Button>
