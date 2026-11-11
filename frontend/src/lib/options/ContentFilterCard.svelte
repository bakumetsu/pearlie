<script lang="ts">
	import Switch from "../components/Switch.svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	let { store = options }: { store?: OptionsStore } = $props();

	const allowBlurred = $derived(store.values?.allow_blurred_tags ?? false);

	function toggleAllowBlurred() {
		store.set({ allow_blurred_tags: !allowBlurred });
	}
</script>

<section class="card">
	<h2 class="card-title">Content filter</h2>

	<div class="row">
		<div class="row-text">
			<span class="row-label">Allow blurred tags in safe mode</span>
			<span class="row-hint">Warn-list posts stay blurred, never hidden, while safe mode is on</span>
		</div>
		<Switch checked={allowBlurred} label="Allow blurred tags in safe mode" onclick={toggleAllowBlurred} />
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
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		margin-bottom: 0.5rem;
	}
	.row-text {
		display: flex;
		flex-direction: column;
	}
	.row-label {
		font-size: 0.9rem;
	}
	.row-hint {
		font-size: 0.8rem;
		color: var(--muted, #a3a3ad);
	}
</style>
