<script lang="ts">
	import Switch from "../components/Switch.svelte";
	import Backdrop from "../components/Backdrop.svelte";
	import { BACKDROP_DEFAULTS } from "./backdrop";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	const strength = $derived(store.values?.backdrop_strength ?? BACKDROP_DEFAULTS.strength);
	const wallOn = $derived(store.values?.backdrop_wall ?? BACKDROP_DEFAULTS.wall);
	const itemOn = $derived(store.values?.backdrop_item ?? BACKDROP_DEFAULTS.item);
	const lightboxOn = $derived(store.values?.backdrop_lightbox ?? BACKDROP_DEFAULTS.lightbox);

	const SAMPLE =
		"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%23ff6b6b'/%3E%3Cstop offset='50%25' stop-color='%234ecdc4'/%3E%3Cstop offset='100%25' stop-color='%2345b7d1'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='320' height='180' fill='url(%23g)'/%3E%3C/svg%3E";

	function onStrengthInput(e: Event) {
		const n = Number((e.target as HTMLInputElement).value);
		store.set({ backdrop_strength: n });
	}

	function toggleWall() {
		store.set({ backdrop_wall: !wallOn });
	}

	function toggleItem() {
		store.set({ backdrop_item: !itemOn });
	}

	function toggleLightbox() {
		store.set({ backdrop_lightbox: !lightboxOn });
	}
</script>

<section class="card live" aria-label="Live preview">
	<h2>Live preview <span class="live-on"><i></i>updates as you edit</span></h2>
	<div class="live-body">
		<div data-testid="backdrop-preview" class="preview">
			{#if strength > 0}
				<Backdrop src={SAMPLE} strength={strength} />
			{/if}
			<img src={SAMPLE} alt="Preview" class="preview-img" />
		</div>
		<small class="live-cap">Placeholder picture over its blurred backdrop.</small>
	</div>
</section>

<section class="card">
	<h2 class="card-title">Image viewer</h2>
	<p class="hint">How a single opened image sits on the page.</p>

	<div class="row">
		<div class="row-text">
			<label class="row-label" for="backdrop-strength">Backdrop strength</label>
			<span class="row-hint">Blurred copy behind the image. 0 = plain dark.</span>
		</div>
		<div class="slider">
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
	</div>

	<div class="row">
		<span class="row-label">Show backdrop in wall overlay</span>
		<Switch checked={wallOn} label="Show backdrop in wall overlay" onclick={toggleWall} />
	</div>

	<div class="row">
		<span class="row-label">Show backdrop on item page</span>
		<Switch checked={itemOn} label="Show backdrop on item page" onclick={toggleItem} />
	</div>

	<div class="row">
		<div class="row-text">
			<span class="row-label">Show backdrop in lightbox</span>
			<span class="row-hint">Takes effect once the lightbox exists.</span>
		</div>
		<Switch checked={lightboxOn} label="Show backdrop in lightbox" onclick={toggleLightbox} />
	</div>
</section>

<style>
	.preview {
		width: 100%;
		max-width: 238px;
		height: 150px;
		position: relative;
		overflow: hidden;
		border-radius: var(--r-md);
		border: 1px solid var(--line);
		background: #000;
	}
	.preview-img {
		position: absolute;
		z-index: 1;
		left: 50%;
		top: 50%;
		height: 84%;
		width: auto;
		transform: translate(-50%, -50%);
		border-radius: 4px;
	}
</style>
