<script lang="ts">
	import { onDestroy, onMount } from "svelte";
	import { getApi } from "../api/client";
	import { createUpdate } from "../stores/update.svelte";
	import Icon from "../components/Icon.svelte";
	import ChangeGroups from "./ChangeGroups.svelte";

	// Options search renders this card too: fetch only when its section is open.
	let { active = true }: { active?: boolean } = $props();

	const update = createUpdate(getApi());
	onMount(() => {
		if (active) void update.openChangelog();
	});
	onDestroy(() => update.dispose());

	const cl = $derived(update.changelog);
	const checkOff = $derived(update.status != null && !update.status.check_enabled);

	function fmtDate(iso: string): string {
		const d = new Date(`${iso}T00:00:00Z`);
		if (Number.isNaN(d.getTime())) return iso;
		return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
	}
</script>

<section class="card cl">
	<div class="cl-top">
		<h2>Changelog</h2>
		<span class="cl-seg">
			<button
				class="seg"
				aria-label="Changelog Main"
				aria-pressed={update.viewChannel === "main"}
				onclick={() => update.setView("main")}
			>Main</button>
			<button
				class="seg"
				aria-label="Changelog Dev"
				aria-pressed={update.viewChannel === "dev"}
				onclick={() => update.setView("dev")}
			>Dev</button>
		</span>
	</div>

	{#if checkOff && cl}
		<p class="muted note">Update check is off. Showing saved data.</p>
	{:else if cl?.stale}
		<p class="muted note">Showing saved data</p>
	{/if}

	{#if update.changelogLoading && !cl}
		<div class="skeleton" aria-busy="true" aria-label="Loading changelog">
			<span></span><span></span><span></span>
		</div>
	{:else if update.changelogFailed || (cl && cl.unavailable)}
		<div class="empty">
			<p class="muted">Changelog unavailable.{checkOff ? " Update checks are off." : ""}</p>
			<button class="iconbtn" aria-label="Retry" title="Retry" onclick={() => update.loadChangelog()}>
				<Icon name="refresh" />
			</button>
		</div>
	{:else if cl}
		{#each update.releases as b, i (b.title)}
			<details class="cl-block" open={i === 0}>
				<summary>
					<span class="ver">{b.version ?? b.title}</span>
					{#if b.date}<span class="muted date">{fmtDate(b.date)}</span>{/if}
					<span class="pill" class:dev={b.version == null}>{b.version == null ? "Dev" : "Main"}</span>
					<small class="muted count">{b.total} {b.total === 1 ? "change" : "changes"}</small>
				</summary>
				<ChangeGroups {b} />
			</details>
		{/each}
		{#if update.hasMore}
			<div class="more">
				<button class="btn" disabled={update.loadingMore} onclick={() => update.loadMore()}>
					{#if update.loadingMore}<span class="spin"><Icon name="refresh" size={16} /></span>{/if}
					{update.moreError ? "Retry" : "Load more"}
				</button>
				{#if update.moreError}<span class="muted">Could not load older releases.</span>{/if}
			</div>
		{/if}
	{/if}
</section>

<style>
	.cl {
		font-size: var(--t-13);
	}
	.cl-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
	}
	.cl-top h2 {
		margin: 0;
	}
	.cl-seg {
		display: inline-flex;
	}
	.note {
		margin: var(--s-2) 0;
	}
	.cl-block {
		border-top: 1px solid var(--line);
	}
	.cl-block summary {
		min-height: 44px;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		cursor: pointer;
	}
	.ver {
		font-weight: 600;
	}
	.count {
		margin-left: auto;
	}
	@media (max-width: 520px) {
		.count {
			display: none;
		}
	}
	.pill {
		background: var(--accent-bg);
		color: var(--accent);
		font-size: var(--t-12);
		border-radius: 999px;
		padding: 2px var(--s-2);
	}
	.pill.dev {
		background: var(--ok-bg);
		color: var(--ok-fg);
	}
	.muted {
		color: var(--muted);
	}
	.seg {
		background: transparent;
		border: 1px solid var(--line-strong);
		color: var(--muted);
		border-radius: 0;
		min-width: 44px;
		min-height: 44px;
		padding: 0 var(--s-2);
		font-size: var(--t-13);
		cursor: pointer;
	}
	.seg[aria-pressed="true"] {
		background: var(--accent);
		color: var(--on-accent);
	}
	.more {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		margin-top: var(--s-3);
	}
	.more .btn {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
	}
	.empty {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.skeleton {
		display: grid;
		gap: var(--s-2);
		margin-top: var(--s-3);
	}
	.skeleton span {
		height: 44px;
		border-radius: var(--r-sm);
		background: var(--line);
	}
	.spin {
		display: inline-flex;
		animation: cl-spin 1s linear infinite;
	}
	@keyframes cl-spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
