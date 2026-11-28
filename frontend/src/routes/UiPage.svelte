<script lang="ts">
  // Dev-only primitive gallery at /__ui. Loaded by dynamic import from App.svelte, so old screens never load app.css.
  import "../app.css";
  import { onMount } from "svelte";
  import Button from "../lib/ui/Button.svelte";
  import IconButton from "../lib/ui/IconButton.svelte";
  import Input from "../lib/ui/Input.svelte";
  import Textarea from "../lib/ui/Textarea.svelte";
  import Select from "../lib/ui/Select.svelte";
  import Switch from "../lib/ui/Switch.svelte";
  import Slider from "../lib/ui/Slider.svelte";
  import Checkbox from "../lib/ui/Checkbox.svelte";
  import RadioGroup from "../lib/ui/RadioGroup.svelte";
  import Badge from "../lib/ui/Badge.svelte";
  import Card from "../lib/ui/Card.svelte";
  import Separator from "../lib/ui/Separator.svelte";
  import Skeleton from "../lib/ui/Skeleton.svelte";
  import Tabs from "../lib/ui/Tabs.svelte";
  import Tooltip from "../lib/ui/Tooltip.svelte";
  import Popover from "../lib/ui/Popover.svelte";
  import DropdownMenu from "../lib/ui/DropdownMenu.svelte";
  import Dialog from "../lib/ui/Dialog.svelte";
  import Sheet from "../lib/ui/Sheet.svelte";
  import AlertDialog from "../lib/ui/AlertDialog.svelte";
  import Toaster from "../lib/ui/Toaster.svelte";
  import { undoToast } from "../lib/ui/undoToast";
  import Tile from "../lib/ui/Tile.svelte";
  import SiteMark from "../lib/ui/SiteMark.svelte";
  import ChipField from "../lib/ui/ChipField.svelte";
  import PageHeader from "../lib/ui/PageHeader.svelte";
  import EmptyState from "../lib/ui/EmptyState.svelte";
  import { toasts } from "../lib/stores/toasts.svelte";
  import type { Chip } from "../lib/query";

  let theme = $state<"dark" | "light">("dark");
  let checked = $state(true);
  let on = $state(true);
  let radio = $state("a");
  let tab = $state("one");
  let menu = $state("newest");
  let dialog = $state(false);
  let sheet = $state(false);
  let side = $state(false);
  let alert = $state(false);
  let popover = $state(false);
  let chips = $state<Chip[]>([]);
  let pending = $state("");
  let slider = $state(50);
  let text = $state("");

  const prev = typeof document === "undefined" ? null : document.documentElement.getAttribute("data-theme");
  $effect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  });
  onMount(() => () => {
    if (prev === null) document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", prev);
  });
</script>

<div class="ui-root min-h-screen bg-background p-4 text-foreground md:p-8">
  <div class="mx-auto flex max-w-3xl flex-col gap-6">
    <PageHeader title="UI primitives">
      {#snippet actions()}
        <Button variant="outline" onclick={() => (theme = theme === "dark" ? "light" : "dark")}>Theme: {theme}</Button>
      {/snippet}
    </PageHeader>

    <Card class="flex flex-col gap-3 p-4">
      <h2 class="font-semibold">Buttons</h2>
      <div class="flex flex-wrap gap-2">
        <Button variant="default">Save</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Delete</Button>
        <Button variant="pill" aria-pressed="true">Pill</Button>
        <Button variant="chip">Chip</Button>
        <Button disabled>Disabled</Button>
        <IconButton icon="search" label="Search" />
      </div>
    </Card>

    <Card class="flex flex-col gap-3 p-4">
      <h2 class="font-semibold">Fields</h2>
      <Input bind:value={text} placeholder="Input" aria-label="Input" />
      <Input shape="pill" placeholder="Pill input" aria-label="Pill input" />
      <Textarea placeholder="Textarea" aria-label="Textarea" />
      <Select aria-label="Select" bind:value={menu}>
        <option value="newest">Newest</option>
        <option value="oldest">Oldest</option>
      </Select>
      <ChipField {chips} onchange={(c) => (chips = c)} bind:pending />
      <div class="flex flex-wrap items-center gap-4">
        <Switch checked={on} label="Switch" onclick={() => (on = !on)} />
        <Checkbox bind:checked label="Checkbox" />
        <Slider bind:value={slider} aria-label="Slider" />
      </div>
      <RadioGroup bind:value={radio} label="Radio" options={[{ value: "a", label: "Alpha" }, { value: "b", label: "Beta" }, { value: "c", label: "Gamma" }]} />
    </Card>

    <Card class="flex flex-col gap-3 p-4">
      <h2 class="font-semibold">Display</h2>
      <div class="flex flex-wrap items-center gap-2">
        <Badge>Badge</Badge>
        <SiteMark id="danbooru" name="Danbooru" />
        <Tooltip text="Tooltip text"><Button variant="outline">Hover or focus</Button></Tooltip>
      </div>
      <Separator />
      <Skeleton class="h-6 w-1/2" />
      <Tabs bind:value={tab} label="Demo tabs" tabs={[{ value: "one", label: "One" }, { value: "two", label: "Two" }]}>
        {#snippet panel(v)}Panel {v}{/snippet}
      </Tabs>
      <div class="grid grid-cols-3 gap-2">
        <Tile caption="Tile one" alt="Tile one" />
        <Tile caption="Tile two" alt="Tile two" selected />
        <Tile caption="Tile three" alt="Tile three" />
      </div>
      <EmptyState title="Nothing here" text="Empty state text." />
    </Card>

    <Card class="flex flex-wrap gap-2 p-4">
      <Popover bind:open={popover} label="Popover">
        {#snippet trigger()}Popover{/snippet}
        Popover content
      </Popover>
      <DropdownMenu bind:value={menu} label="Sort" options={[{ value: "newest", label: "Newest" }, { value: "oldest", label: "Oldest" }, { value: "random", label: "Random" }]}>
        {#snippet trigger(current)}Sort: {current}{/snippet}
      </DropdownMenu>
      <Button variant="outline" onclick={() => (dialog = true)}>Dialog</Button>
      <Button variant="outline" onclick={() => (sheet = true)}>Sheet</Button>
      <Button variant="outline" onclick={() => (side = true)}>Side panel</Button>
      <Button variant="destructive" onclick={() => (alert = true)}>Alert</Button>
      <Button variant="outline" onclick={() => undoToast("Moved to trash", () => toasts.push({ kind: "info", message: "Restored" }))}>Undo toast</Button>
    </Card>
  </div>

  <Dialog bind:open={dialog} title="Dialog" description="Escape closes it.">Dialog body</Dialog>
  <Sheet bind:open={sheet} title="Sheet">Sheet body</Sheet>
  <Sheet bind:open={side} side="right" title="Side panel">Panel body</Sheet>
  <AlertDialog bind:open={alert} title="Delete item?" description="It goes to trash." confirmLabel="Delete" destructive onconfirm={() => undoToast("Moved to trash", () => {})} />
  <Toaster />
</div>
