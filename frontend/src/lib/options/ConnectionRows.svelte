<script lang="ts">
	import { connections } from "../stores/connections.svelte";
	import type { ConnectionsStore } from "../stores/connections.svelte";
	import { getApi } from "../api/client";
	import type { Api } from "../api/client";
	import ConnectionPopup from "./ConnectionPopup.svelte";

	let {
		title,
		names,
		store = connections,
		api = getApi()
	}: {
		title: string;
		names: { key: string; label: string }[];
		store?: ConnectionsStore;
		api?: Api;
	} = $props();

	let editing = $state<string | null>(null);

	store.load(api);

	function editingLabel(): string {
		return names.find((n) => n.key === editing)?.label ?? "";
	}
</script>

<section class="card">
	<h2 class="card-title">{title}</h2>

	{#each names as { key, label } (key)}
		<div class="row">
			<span class="row-label">{label}</span>
			<span class="chip"
				>{store.loading ? "missing" : store.byName(key)?.key === "set" ? "set" : "missing"}</span
			>
			{#if store.byName(key)?.address}
				<span class="muted">{store.byName(key)?.address}</span>
			{/if}
			{#if store.restartNeeded[key]}
				<span class="muted">Restart Pearlie to apply</span>
			{/if}
			<button
				class="btn"
				aria-label={`Test ${label}`}
				disabled={store.testing[key]}
				on:click={() => store.test(api, key)}
			>
				{store.testing[key] ? "Testing..." : "Test"}
			</button>
			<span class="result{store.results[key] && !store.results[key]!.ok ? " err" : ""}" role="status"
				>{store.results[key]?.message}</span
			>
			<button class="btn" aria-label={`Edit ${label}`} on:click={() => (editing = key)}>✎</button>
		</div>
	{/each}
</section>

{#if editing}
	<ConnectionPopup
		name={editing}
		label={editingLabel()}
		{store}
		{api}
		onclose={() => (editing = null)}
	/>
{/if}

<style>
	.card {
		border: 1px solid var(--border, #333);
		border-radius: var(--radius, 8px);
		padding: var(--pad, 16px);
	}
	.card-title {
		margin: 0 0 var(--pad, 16px);
		font-size: 1.1rem;
	}
	.row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		min-height: 44px;
		margin-bottom: 0.5rem;
	}
	.row-label {
		font-size: 0.9rem;
	}
	.muted {
		font-size: 0.8rem;
		color: var(--muted, #999);
	}
	.chip {
		display: inline-flex;
		align-items: center;
		min-height: 22px;
		padding: 0 0.5rem;
		border: 1px solid var(--muted, #555);
		border-radius: 999px;
		font-size: 0.7rem;
		color: var(--muted, #999);
	}
	.result {
		font-size: 0.8rem;
		color: var(--muted, #999);
	}
	.result.err {
		color: var(--error, #ff6b6b);
	}
	.btn {
		min-height: 44px;
		min-width: 44px;
		padding: 0 0.5rem;
		border: 1px solid var(--border, #333);
		border-radius: 4px;
		background: var(--input-bg, #111);
		color: inherit;
		cursor: pointer;
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
