<script lang="ts">
  import { getRouter } from "../ctx";
  import { linkClick } from "../router";
  import { pageSrc } from "../reader/pages";
  import { gatedSrc } from "../webImageQueue";

  let {
    thumbTpl,
    count,
    last,
    hrefFor,
    onopen,
  }: {
    thumbTpl: string;
    count: number;
    last: number | null;
    hrefFor?: (n: number) => string;
    onopen?: (n: number) => void;
  } = $props();

  const router = getRouter();
  const pages = $derived(Array.from({ length: count }, (_, i) => i + 1));
  const src = (n: number) => ({ src: pageSrc(thumbTpl, n), prio: n <= 6 ? ("focus" as const) : ("prefetch" as const) });
</script>

<ul class="grid">
  {#each pages as n (n)}
    <li>
      {#if hrefFor}
        <a class="thumb" class:last={last === n} href={hrefFor(n)} aria-label={"Page " + n} onclick={(e) => linkClick(e, router)}>
          <img alt="" use:gatedSrc={src(n)} />
        </a>
      {:else}
        <button class="thumb" class:last={last === n} type="button" aria-label={"Page " + n} onclick={() => onopen?.(n)}>
          <img alt="" use:gatedSrc={src(n)} />
        </button>
      {/if}
    </li>
  {/each}
</ul>

<style>
  .grid { list-style: none; margin: var(--s-5) 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(max(88px, calc((100% - 32px) / 5)), 1fr)); gap: var(--s-2); }
  .thumb { display: block; width: 100%; padding: 0; aspect-ratio: 2 / 3; background: var(--surface); border-radius: var(--r-sm); overflow: hidden; border: 2px solid transparent; cursor: pointer; }
  .thumb.last { border-color: var(--progress); }
  .thumb:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
</style>
