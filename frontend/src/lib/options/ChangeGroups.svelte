<script lang="ts">
	import type { ChangeBlock } from "../api/client";

	let { b }: { b: ChangeBlock } = $props();
</script>

{#each b.groups as g (g.kind)}
	<p class="cl-kind"><span class="dot {g.kind.toLowerCase()}"></span>{g.kind}</p>
	<ul class="cl-list">
		{#each g.items as it, i (i)}
			<li>{it}</li>
		{/each}
	</ul>
{:else}
	<p class="muted">No notable changes</p>
{/each}
{#if b.groups.length === 0 && b.more_url}
	<a class="cl-more" href={b.more_url} target="_blank" rel="noopener noreferrer">See on GitHub</a>
{/if}
{#if b.more > 0 && b.more_url}
	<a class="cl-more" href={b.more_url} target="_blank" rel="noopener noreferrer">+ {b.more} more on GitHub</a>
{/if}

<style>
	.cl-kind {
		display: flex;
		align-items: center;
		gap: var(--s-1);
		margin: var(--s-2) 0 var(--s-1);
		color: var(--muted);
		font-size: var(--t-12);
	}
	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--muted);
	}
	.dot.added {
		background: var(--ok-fg);
	}
	.dot.fixed {
		background: var(--progress);
	}
	.dot.reworked {
		background: var(--accent);
	}
	.cl-list {
		margin: 0;
		padding-left: var(--s-3);
		overflow-wrap: anywhere;
	}
	.cl-more {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--accent);
	}
	.muted {
		color: var(--muted);
	}
</style>
