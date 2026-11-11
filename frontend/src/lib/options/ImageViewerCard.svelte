<script lang="ts">
	import Switch from "../components/Switch.svelte";
	import Backdrop from "../components/Backdrop.svelte";
	import { BACKDROP_DEFAULTS } from "./backdrop";
	import { untrack } from "svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	let strength = $state(untrack(() => store.values?.backdrop_strength ?? BACKDROP_DEFAULTS.strength));
	let wallOn = $state(untrack(() => store.values?.backdrop_wall ?? BACKDROP_DEFAULTS.wall));
	let itemOn = $state(untrack(() => store.values?.backdrop_item ?? BACKDROP_DEFAULTS.item));
	let lightboxOn = $state(untrack(() => store.values?.backdrop_lightbox ?? BACKDROP_DEFAULTS.lightbox));

	$effect(() => {
		const v = store.values;
		if (v) {
			strength = v.backdrop_strength;
			wallOn = v.backdrop_wall;
			itemOn = v.backdrop_item;
			lightboxOn = v.backdrop_lightbox;
		}
	});

	const SAMPLE =
		"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%23ff6b6b'/%3E%3Cstop offset='50%25' stop-color='%234ecdc4'/%3E%3Cstop offset='100%25' stop-color='%2345b7d1'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='320' height='180' fill='url(%23g)'/%3E%3C/svg%3E";

	function onStrengthInput(e: Event) {
		const n = Number((e.target as HTMLInputElement).value);
		strength = n;
		store.set({ backdrop_strength: n });
	}

	function toggleWall() {
		wallOn = !wallOn;
		store.set({ backdrop_wall: wallOn });
	}

	function toggleItem() {
		itemOn = !itemOn;
		store.set({ backdrop_item: itemOn });
	}

	function toggleLightbox() {
		lightboxOn = !lightboxOn;
		store.set({ backdrop_lightbox: lightboxOn });
	}
</script>

<section class="card">
	<h2 class="card-title">Image viewer</h2>

	<div data-testid="backdrop-preview" class="preview">
		{#if strength > 0}
			<Backdrop src={SAMPLE} strength={strength} />
		{/if}
		<img src={SAMPLE} alt="Preview" class="preview-img" />
	</div>

	<div class="row">
		<label class="row-label" for="backdrop-strength">Backdrop strength</label>
		<input
			id="backdrop-strength"
			type="range"
			min={0}
			max={100}
			step={1}
			aria-label="Backdrop strength"
			value={strength}
			oninput={onStrengthInput}
		/>
		<span class="row-value">{strength}</span>
	</div>

	<div class="row">
		<span class="row-label">Wall overlay</span>
		<Switch checked={wallOn} label="Wall overlay" onclick={toggleWall} />
	</div>

	<div class="row">
		<span class="row-label">Item page</span>
		<Switch checked={itemOn} label="Item page" onclick={toggleItem} />
	</div>

	<div class="row">
		<span class="row-label">Lightbox</span>
		<Switch checked={lightboxOn} label="Lightbox" onclick={toggleLightbox} />
	</div>
</section>

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
	.preview {
		aspect-ratio: 16 / 9;
		border-radius: var(--radius, 8px);
		position: relative;
		overflow: hidden;
		background: #000;
		margin-bottom: var(--pad, 16px);
	}
	.preview-img {
		position: relative;
		z-index: 1;
		width: 50%;
		margin: 25% auto;
		display: block;
	}
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.5rem;
	}
	.row-label {
		font-size: 0.9rem;
	}
	.row-value {
		min-width: 2ch;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
</style>
