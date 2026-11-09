<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '../lib/components/Icon.svelte';
	import type { IconName } from '../lib/components/Icon.svelte';
	import { getApi } from '../lib/api/client';
	import { createTrash } from '../lib/stores/trash.svelte';
	import { expiresLabel } from '../lib/trash/format';
	import { seeAllGrid } from '../lib/stores/shared.svelte';

	const trash = createTrash(getApi(), { onRestored: () => seeAllGrid.reset() });

	let h1: HTMLHeadingElement;

	onMount(() => {
		h1.focus();
		trash.refresh();
	});

	function kindIcon(kind: string): IconName {
		switch (kind) {
			case 'image':
				return 'image';
			case 'video':
				return 'film';
			case 'book':
				return 'book';
			case 'series':
				return 'library';
			default:
				return 'image';
		}
	}
</script>

<div class="content">
	<h1 tabindex="-1" bind:this={h1}>Trash</h1>

	{#if trash.items.length > 0}
		<p class="muted">Items are deleted for good after {trash.items[0].retention_days} days.</p>
	{/if}

	{#if trash.offline}
		<div class="offline" role="status">
			<Icon name="alert" size={16} />
			<span>Offline, retrying</span>
		</div>
	{/if}

	{#if !trash.loaded}
		<div class="skel"></div>
		<div class="skel"></div>
		<div class="skel"></div>
	{:else if trash.items.length === 0}
		<p class="empty">Trash is empty</p>
	{:else}
		<div class="header-bar">
			{#if !trash.confirming}
				<button class="btn" onclick={trash.askEmpty}>
					<Icon name="trash" size={16} />
					<span>Empty trash</span>
				</button>
			{/if}
			{#if trash.confirming}
				<div class="confirm" role="alert">
					<span>Empty trash? {trash.items.length} items, can't undo</span>
					<button class="btn" onclick={trash.cancelEmpty}>Cancel</button>
					<button class="btn danger" onclick={trash.confirmEmpty}>Confirm</button>
				</div>
			{/if}
		</div>

		<ul class="list">
			{#each trash.items as t (t.token)}
				<li class="row">
					<Icon name={kindIcon(t.item.kind)} size={20} />
					<div class="text">
						<span class="title">{t.item.title}</span>
						<span class="muted">{expiresLabel(t.expires_at)}</span>
					</div>
					<div class="actions">
						<button aria-label={`Restore ${t.item.title}`} onclick={() => trash.restore(t.token)}>
							<Icon name="undo" size={16} />
						</button>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.content {
		max-width: 720px;
		margin: 0 auto;
		padding: 1.5rem 1rem;
	}

	h1 {
		font-size: 1.5rem;
		margin: 0 0 0.5rem;
		outline: none;
	}

	.muted {
		color: var(--muted);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.offline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius, 6px);
		background: var(--surface, #f5f5f5);
		border: 1px solid var(--border, #ddd);
		margin-bottom: 1rem;
		font-size: 0.875rem;
	}

	.header-bar {
		margin-bottom: 0.75rem;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		min-height: 44px;
		padding: 0 0.75rem;
		border: 1px solid var(--border, #ddd);
		border-radius: var(--radius, 6px);
		background: var(--surface, #fff);
		color: var(--fg, #111);
		font-size: 0.875rem;
		cursor: pointer;
	}

	.btn:hover {
		background: var(--surface-hover, #f0f0f0);
	}

	.danger {
		background: var(--danger-bg, #fee);
		color: var(--danger-fg, #c00);
		border-color: var(--danger-bg, #fee);
	}

	.danger:hover {
		opacity: 0.9;
	}

	.confirm {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		background: var(--surface, #fff);
		border: 1px solid var(--border, #ddd);
		border-radius: var(--radius, 6px);
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
	}

	.list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.row {
		display: grid;
		grid-template-columns: 28px 1fr auto;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--border, #eee);
	}

	.row:last-child {
		border-bottom: none;
	}

	.text {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.title {
		font-size: 0.9375rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.actions button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border: none;
		background: transparent;
		border-radius: var(--radius, 6px);
		cursor: pointer;
		color: var(--fg, #111);
	}

	.actions button:hover {
		background: var(--surface-hover, #f0f0f0);
	}

	.skel {
		height: 72px;
		background: var(--line);
		border-radius: var(--r-md);
	}

	.empty {
		text-align: center;
		color: var(--muted);
		padding: 2rem 0;
		font-size: 0.9375rem;
	}
</style>
