<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '../lib/components/Icon.svelte';
	import type { IconName } from '../lib/components/Icon.svelte';
	import { getApi } from '../lib/api/client';
	import { createTrash } from '../lib/stores/trash.svelte';
	import { expiresLabel } from '../lib/trash/format';
	import { resetAllGrids } from '../lib/stores/shared.svelte';

	const trash = createTrash(getApi(), { onRestored: () => resetAllGrids() });

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

	{#if trash.retentionDays !== null}
		<p class="muted">Items are deleted for good after {trash.retentionDays} days.</p>
	{/if}

	{#if trash.offline}
		<div class="offline" role="status">
			<Icon name="alert" size={16} />
			<span>Offline, retrying</span>
		</div>
	{:else if trash.error}
		<div class="offline" role="status">
			<Icon name="alert" size={16} />
			<span>{trash.error}</span>
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
		border-radius: var(--r-sm);
		background: var(--surface);
		border: 1px solid var(--line);
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
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: var(--surface);
		color: var(--text);
		font-size: 0.875rem;
		cursor: pointer;
	}

	.btn:hover {
		background: var(--line);
	}

	.danger {
		background: var(--danger-bg);
		color: var(--danger-fg);
		border-color: var(--danger-bg);
	}

	button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.danger:hover {
		opacity: 0.9;
	}

	.confirm {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
	}

	.list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}

	.row {
		display: grid;
		grid-template-columns: 28px 1fr auto;
		gap: var(--s-3);
		align-items: center;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--r-md);
		padding: var(--s-3);
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
		border: 1px solid var(--line);
		background: transparent;
		border-radius: var(--r-sm);
		cursor: pointer;
		color: var(--text);
	}

	.actions button:hover {
		background: var(--line);
	}

	.skel {
		height: 72px;
		background: var(--line);
		border-radius: var(--r-md);
	}

	.empty {
		color: var(--muted);
		margin: 0;
		font-size: 0.9375rem;
	}
</style>
