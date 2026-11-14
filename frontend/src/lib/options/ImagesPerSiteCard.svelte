<script lang="ts">
	import { untrack } from "svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	const current = $derived(store.values?.images_per_site ?? 10);

	let draft = $state<number | string>(untrack(() => current));
	let error: string = $state("");

	$effect(() => {
		if (error) return;
		draft = current;
	});

	function handleChange(e: Event) {
		const input = e.target as HTMLInputElement;
		const n = Number(input.value);
		if (!Number.isInteger(n) || n < 1 || n > 16) {
			error = "Enter a whole number from 1 to 16";
			draft = input.value;
			return;
		}
		error = "";
		draft = n;
		if (n !== current) store.set({ images_per_site: n });
	}
</script>

<section class="card">
	<h2 class="card-title">Browsing</h2>
	<p class="hint">Images loaded at a time per site. A site that says slow down gets fewer.</p>
	<div class="row">
		<label class="row-label" for="images-per-site">Images at a time</label>
		<span class="muted">default 10</span>
		<input
			id="images-per-site"
			type="number"
			inputmode="numeric"
			min={1}
			max={16}
			step={1}
			data-testid="images-per-site"
			aria-label="Images at a time per site"
			value={draft}
			onchange={handleChange}
		/>
	</div>
	{#if error}<span class="err" role="alert">{error}</span>{/if}
</section>
