<script lang="ts">
	import Switch from "../components/Switch.svelte";
	import { SITE_ORDER } from "../query";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	const hidden = $derived(store.values?.hidden_sites ?? []);

	// The last visible site stays on, so Discover always has a site.
	const lastOn = $derived(SITE_ORDER.filter((s) => !hidden.includes(s.id)).length <= 1);

	function toggle(id: string) {
		if (lastOn && !hidden.includes(id)) return;
		const next = hidden.includes(id) ? hidden.filter((s) => s !== id) : [...hidden, id];
		store.set({ hidden_sites: next });
	}
</script>

<section class="card">
	<h2 class="card-title">Discover rail</h2>
	<div class="rail" role="group" aria-labelledby="rail-title">
		<h3 id="rail-title" class="rail-title">Sites in the rail</h3>
		<p class="hint">A hidden site leaves the Discover rail. Your saved searches keep it.</p>
		{#if lastOn}
			<p class="hint">At least one site stays on.</p>
		{/if}
		{#each SITE_ORDER as s (s.id)}
			{@const label = `Show ${s.label} in rail`}
			<div class="rail-line">
				<span>{s.label}</span>
				<Switch
					checked={!hidden.includes(s.id)}
					{label}
					disabled={lastOn && !hidden.includes(s.id)}
					onclick={() => toggle(s.id)}
				/>
			</div>
		{/each}
	</div>
	<div class="row">
		<span class="row-label">Show site names</span>
		<Switch
			checked={store.values?.site_names ?? true}
			label="Show site names on pills"
			onclick={() => store.set({ site_names: !(store.values?.site_names ?? true) })}
		/>
	</div>
	<p class="hint">Off: pills show the icon only.</p>
	<div class="row">
		<span class="row-label">Tapped site first</span>
		<Switch
			checked={store.values?.tapped_first ?? false}
			label="Show the last tapped site first"
			onclick={() => store.set({ tapped_first: !(store.values?.tapped_first ?? false) })}
		/>
	</div>
	<p class="hint">On: the site you tapped last becomes the first row. The rest keep the pill order. Forgotten when you close the app.</p>
</section>

<style>
	.rail-title {
		margin: 0;
		padding: 16px 16px 2px;
		border-top: 1px solid #2c2c33;
		font-size: var(--t-15);
		font-weight: 600;
	}
	.rail-line {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		min-height: 44px;
		margin: 0 16px;
		padding: 0 0 0 16px;
	}
</style>
