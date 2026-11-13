<script lang="ts">
	import Switch from "../components/Switch.svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	const on = $derived(store.values?.infinite_scroll ?? false);
</script>

<section class="card">
	<h2 class="card-title">Lists</h2>
	<p class="hint">How long lists open: See all, Images, Videos, Series and Books.</p>

	<div class="row">
		<div class="row-text">
			<span class="row-label">Infinite scroll</span>
			<span class="row-hint">Load the next page near the end instead of page buttons.</span>
		</div>
		<Switch checked={on} label="Infinite scroll" onclick={() => store.set({ infinite_scroll: !on })} />
	</div>
</section>
