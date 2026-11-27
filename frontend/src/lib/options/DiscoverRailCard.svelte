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
	<div class="row stack">
		<span class="row-label">
			Sites in the rail<br />
			<span class="muted">Sites that show as pills in Discover.{lastOn ? " At least one stays on." : ""}</span>
		</span>
		<div class="rail-list" role="group" aria-label="Sites in the rail">
			{#each SITE_ORDER as s (s.id)}
				{@const label = `Show ${s.label} in rail`}
				<span class="rail-site">
					<span>{s.label}</span>
					<Switch
						checked={!hidden.includes(s.id)}
						{label}
						disabled={lastOn && !hidden.includes(s.id)}
						onclick={() => toggle(s.id)}
					/>
				</span>
			{/each}
		</div>
	</div>
	<div class="row">
		<span class="row-label">Show site names</span>
		<Switch
			checked={store.values?.site_names ?? true}
			label="Show site names on pills"
			onclick={() => store.set({ site_names: !(store.values?.site_names ?? true) })}
		/>
	</div>
	<div class="row">
		<span class="row-label">Tapped site first</span>
		<Switch
			checked={store.values?.tapped_first ?? false}
			label="Show the last tapped site first"
			onclick={() => store.set({ tapped_first: !(store.values?.tapped_first ?? false) })}
		/>
	</div>
	<p class="hint">On: the site you tapped last becomes the first row. Forgotten when you close the app.</p>
</section>

<style>
	:global(.options .card) .row.stack {
		flex-direction: column;
		align-items: stretch;
		gap: 4px;
	}
	.muted {
		font-size: var(--t-13);
		color: var(--muted);
	}
	.rail-list {
		display: flex;
		flex-direction: column;
	}
	.rail-site {
		display: flex;
		align-items: center;
		justify-content: space-between;
		min-height: 44px;
		padding-left: 16px;
		border-top: 1px solid #2c2c33;
	}
	.rail-site:first-child {
		border-top: 0;
	}
</style>
