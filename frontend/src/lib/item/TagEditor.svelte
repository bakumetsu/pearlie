<script lang="ts">
  import TagChips from "./TagChips.svelte";
  import { getRouter } from "../ctx";
  import { tagSearchHref } from "../query";

  let { tags, onadd, onremove, onreject }: {
    tags: string[];
    onadd: (text: string) => void;
    onremove: (tag: string) => void;
    onreject?: (tag: string) => void;
  } = $props();

  // Pages that run without the app shell (tests) have no router: a tap then does nothing.
  let router: ReturnType<typeof getRouter> | undefined;
  try {
    router = getRouter();
  } catch {
    router = undefined;
  }

  const mode = $derived(onreject ? "reject" : "remove");

  function handleX(name: string): void {
    if (onreject) onreject(name);
    else onremove(name);
  }
</script>

<TagChips
  tags={tags.map((name) => ({ name }))}
  {mode}
  onsearch={(name) => router?.navigate(tagSearchHref(name))}
  onx={handleX}
  {onadd}
/>
