<script lang="ts">
	import { connections } from "../stores/connections.svelte";
	import type { ConnectionsStore } from "../stores/connections.svelte";
	import { getApi } from "../api/client";
	import type { Api } from "../api/client";
	import Icon from "../components/Icon.svelte";
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
		<div class="row conn">
			<span class="row-label">{label}</span>
			<span class="chip"
				>{store.loading ? "missing" : store.byName(key)?.key === "set" ? "set" : "missing"}</span
			>
			{#if store.byName(key)?.address}
				<span class="muted">{store.byName(key)?.address}</span>
			{/if}
			<span class="result{store.results[key] && !store.results[key]!.ok ? " err" : ""}" role="status"
				>{store.results[key]?.message}</span
			>
			<button
				class="btn test-btn"
				aria-label={`Test ${label}`}
				disabled={store.testing[key]}
				onclick={() => store.test(api, key)}
			>
				{store.testing[key] ? "Testing..." : "Test"}
			</button>
			<button class="btn" aria-label={`Edit ${label}`} onclick={() => (editing = key)}><Icon name="settings" size={16} /></button>
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
	.test-btn {
		margin-left: auto;
	}
	.result {
		font-size: var(--t-13);
		color: var(--muted);
	}
	.result.err {
		color: var(--danger-hot);
	}
</style>
