<script lang="ts">
	import Icon from "../components/Icon.svelte";
	import type { Mode, Fit, Dir } from "./pages";
	import type { LibraryItem } from "../api/client";

	let {
		title,
		next,
		hasSeries,
		onnext,
		onback,
	}: {
		title: string;
		next: { title: string; thumb_url: string | null } | null;
		hasSeries: boolean;
		onnext: () => void;
		onback: () => void;
	} = $props();

	const isLastInSeries = $derived(hasSeries && !next);
	const heading = $derived(
		isLastInSeries ? `End of ${title} · last book` : `End of ${title}`,
	);
</script>

<div class="card" data-testid="end-card">
	<p class="heading">{heading}</p>

	{#if next}
		{#if next.thumb_url}
			<img class="thumb" src={next.thumb_url} alt={next.title} height={160} />
		{/if}
		<p class="next-label">Next: {next.title}</p>
		<div class="actions">
			<button class="btn primary" onclick={onnext}>
				<Icon name="chevron-right" size={20} />
				Next book
			</button>
			<button class="btn secondary" onclick={onback}>Back to series</button>
		</div>
	{:else}
		<div class="actions">
			<button class="btn secondary" onclick={onback}>
				<Icon name="arrow-left" size={20} />
				Back
			</button>
		</div>
	{/if}
</div>

<style>
	.card {
		margin: auto;
		padding: 56px 16px 96px;
		text-align: center;
		background: rgb(20 20 24 / 0.82);
		border: 1px solid var(--line-strong);
		border-radius: var(--r-lg);
		backdrop-filter: blur(8px);
		color: var(--t-13);
		font-size: var(--t-13);
	}

	.heading {
		margin: 0 0 var(--s-4);
		font-size: 15px;
		font-weight: 600;
	}

	.thumb {
		height: 160px;
		width: auto;
		display: block;
		margin: 0 auto var(--s-4);
		border-radius: var(--r-sm);
		object-fit: cover;
	}

	.next-label {
		margin: 0 0 var(--s-4);
	}

	.actions {
		display: flex;
		justify-content: center;
		gap: var(--s-3);
	}

	.btn {
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--s-4);
		border-radius: var(--r-md);
		cursor: pointer;
		font: inherit;
		font-size: 14px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--s-2);
		border: 1px solid var(--line-strong);
		background: rgb(30 30 35 / 0.88);
		color: var(--t-13);
		transition: background 0.15s;
	}

	.btn:hover {
		background: var(--line);
	}

	.btn.primary {
		background: var(--accent);
		color: #0b1220;
		border-color: var(--accent);
		font-weight: 600;
	}

	.btn.primary:hover {
		background: #9cc4ff;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
