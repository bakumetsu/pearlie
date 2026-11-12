<script lang="ts">
	import Switch from "../components/Switch.svelte";
	import { SITE_ORDER } from "../query";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	const hidden = $derived(store.values?.hidden_sites ?? []);

	function toggle(id: string) {
		const next = hidden.includes(id) ? hidden.filter((s) => s !== id) : [...hidden, id];
		store.set({ hidden_sites: next });
	}
</script>

<section class="card">
	<h2 class="card-title">Sites in the rail</h2>
	<p class="hint">A hidden site leaves the Discover rail. Your saved searches keep it.</p>

	{#each SITE_ORDER as s (s.id)}
		{@const label = `Show ${s.label} in rail`}
		<div class="row">
			<span class="row-label">{s.label}</span>
			<Switch checked={!hidden.includes(s.id)} {label} onclick={() => toggle(s.id)} />
		</div>
	{/each}
</section>
