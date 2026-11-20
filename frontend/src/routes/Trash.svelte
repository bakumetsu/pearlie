<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '../lib/components/Icon.svelte';
	import type { IconName } from '../lib/components/Icon.svelte';
	import { getApi } from '../lib/api/client';
	import { createTrash } from '../lib/stores/trash.svelte';
	import { daysLeft, formatSize, sideOf } from '../lib/trash/format';
	import { resetAllGrids } from '../lib/stores/shared.svelte';

	const trash = createTrash(getApi(), { onRestored: () => resetAllGrids() });

	let h1: HTMLHeadingElement;

	onMount(() => {
		h1.focus();
		trash.refresh();
	});

	function hueOf(id: string): number {
		let h = 0;
		for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
		return h;
	}

	function kindLabel(kind: string): string {
		return kind === 'series' ? 'Series' : kind === 'book' ? 'Book' : kind === 'video' ? 'Video' : 'Image';
	}

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
	<div class="top">
		<div>
			<h1 tabindex="-1" bind:this={h1}>Trash</h1>
			{#if trash.retentionDays !== null}
				<p class="muted">Deleted for good after {trash.retentionDays} days.</p>
			{/if}
		</div>
		{#if trash.loaded && trash.items.length > 0}
			<button class="btn danger" aria-label="Empty trash" onclick={trash.askEmpty}>
				<Icon name="trash" size={16} />
				<span>Empty trash</span>
			</button>
		{/if}
	</div>

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
		<div class="empty">
			<Icon name="trash" size={28} />
			<b>Trash is empty</b>
			<span>Deleted items stay here for {trash.retentionDays ?? 7} days.</span>
		</div>
	{:else}
		{#each trash.groups as g (g.group ?? g.items[0].token)}
			{#if g.group !== null && g.items.length > 1}
				<div class="eyebrow">
					<span><b>{g.items.length} items</b> deleted together</span>
					<button class="btn accent" aria-label="Restore group" onclick={() => trash.restoreGroup(g.group as string)}>
						<Icon name="undo" size={16} />
						<span>Restore group</span>
					</button>
				</div>
			{/if}
			<ul class="list">
				{#each g.items as t (t.token)}
					{@const left = daysLeft(t.expires_at)}
					<li class="row">
						<div class="plate" style="--h: {hueOf(t.item.id)}"><Icon name={kindIcon(t.item.kind)} size={24} /></div>
						<div class="text">
							<span class="title">{t.item.title}</span>
							<span class="meta">
								<span class="side">{sideOf(t.item.kind)}</span>
								<span>{kindLabel(t.item.kind)}</span>
							</span>
							<span class="meta">
								<span class="dl" class:soon={left < 3}>
									<Icon name="trash" size={12} />{left} {left === 1 ? 'day' : 'days'} left
								</span>
							</span>
						</div>
						<div class="actions">
							<button aria-label={`Restore ${t.item.title}`} onclick={() => trash.restore(t.token)}>
								<Icon name="undo" size={16} />
							</button>
							<button class="del" aria-label={`Delete ${t.item.title} for good`} onclick={() => trash.askDelete(t.token)}>
								<Icon name="x" size={16} />
							</button>
						</div>
					</li>
					{#if trash.confirmingToken === t.token}
						<li class="confirm" role="alert">
							<span class="t">Delete <b>{t.item.title}</b> for good? The file is removed and cannot come back.</span>
							<button class="btn" onclick={trash.cancelDelete}>Cancel</button>
							<button class="btn danger" onclick={trash.confirmDelete}>Delete for good</button>
						</li>
					{/if}
				{/each}
			</ul>
		{/each}
	{/if}
</div>

{#if trash.confirming}
	<div class="modal">
		<div class="dlg" role="alertdialog" aria-modal="true" aria-labelledby="empty-t">
			<b id="empty-t">Empty trash?</b>
			<p class="muted">
				{trash.items.length} {trash.items.length === 1 ? 'item' : 'items'}{trash.totalBytes > 0 ? `, ${formatSize(trash.totalBytes)}` : ''} are deleted for good. This cannot be undone.
			</p>
			<div class="dbtn">
				<button class="btn" onclick={trash.cancelEmpty}>Cancel</button>
				<button class="btn danger" onclick={trash.confirmEmpty}>Empty trash</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.content {
		padding: 1.5rem var(--gutter);
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}

	.top {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--s-3);
	}

	h1 {
		font-size: 1.5rem;
		margin: 0 0 0.25rem;
		outline: none;
	}

	.muted {
		color: var(--muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.offline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		border-radius: var(--r-sm);
		background: var(--surface);
		border: 1px solid var(--line);
		font-size: 0.875rem;
	}

	.eyebrow {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		min-height: 44px;
		font-size: 0.75rem;
		color: var(--muted);
		margin-top: var(--s-2);
	}

	.eyebrow b {
		color: var(--text);
		font-weight: 600;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		min-height: 44px;
		padding: 0 0.75rem;
		border: 1px solid var(--line);
		border-radius: var(--r-md);
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

	.accent {
		background: var(--accent-bg);
		color: var(--accent);
		border-color: var(--accent-bg);
	}

	button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
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
		grid-template-columns: 56px 1fr auto;
		gap: var(--s-3);
		align-items: center;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--r-md);
		padding: var(--s-3);
	}

	.plate {
		width: 56px;
		height: 56px;
		border-radius: var(--r-sm);
		display: flex;
		align-items: center;
		justify-content: center;
		color: rgb(255 255 255 / 0.85);
		background: hsl(var(--h) 28% 30%);
	}

	.text {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}

	.title {
		font-size: 0.9375rem;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 2px 8px;
		font-size: 0.75rem;
		color: var(--muted);
	}

	.side {
		color: var(--text);
	}

	.dl {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}

	.dl.soon {
		color: var(--danger-fg);
		background: var(--danger-bg);
		border-radius: 10px;
		padding: 0 8px;
	}

	.actions {
		display: flex;
		gap: 4px;
	}

	.actions button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border: 1px solid var(--line);
		background: transparent;
		border-radius: var(--r-md);
		cursor: pointer;
		color: var(--text);
	}

	.actions button:hover {
		background: var(--line);
	}

	.actions .del {
		color: var(--danger-fg);
	}

	.confirm {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		background: var(--surface);
		border: 1px solid var(--danger-fg);
		border-radius: var(--r-md);
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
	}

	.confirm .t {
		flex: 1 1 200px;
	}

	.skel {
		height: 72px;
		background: var(--line);
		border-radius: var(--r-md);
	}

	.empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		padding: 48px 0;
		text-align: center;
		color: var(--muted);
		font-size: 0.875rem;
	}

	.empty b {
		color: var(--text);
		font-size: 0.9375rem;
	}

	.modal {
		position: fixed;
		inset: 0;
		z-index: 900;
		background: rgb(0 0 0 / 0.65);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 16px;
	}

	.dlg {
		width: min(360px, 100%);
		background: var(--surface);
		border: 1px solid var(--line-strong);
		border-radius: var(--r-lg, var(--r-md));
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.dlg b {
		font-size: 1.0625rem;
	}

	.dbtn {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 6px;
	}
</style>
