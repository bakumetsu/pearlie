<script lang="ts">
	import { getApi } from "../api/client";
	import type { Api, ScanResult } from "../api/client";
	import Icon from "../components/Icon.svelte";

	let { api = getApi() }: { api?: Api } = $props();

	let busy = $state(false);
	let result = $state<ScanResult | null>(null);
	let error = $state("");

	async function scan() {
		if (busy) return;
		busy = true;
		error = "";
		try {
			result = await api.scanRule34();
		} catch {
			result = null;
			error = "Could not scan the Stash folder";
		} finally {
			busy = false;
		}
	}
</script>

<section class="card">
	<h2 class="card-title">Import older saves</h2>
	<div class="row">
		<span>Scan the Stash rule34 folder</span>
		<button
			type="button"
			class="scan"
			data-testid="import-scan"
			aria-label="Scan rule34 folder"
			title="Scan rule34 folder"
			disabled={busy}
			onclick={scan}
		>
			<Icon name="refresh" />
		</button>
	</div>
	{#if result}
		<p class="hint" data-testid="import-result">
			{result.found} files found, {result.imported} new, {result.skipped} skipped.
		</p>
	{/if}
	{#if error}<span class="err" role="alert">{error}</span>{/if}
</section>

<style>
	.scan {
		min-width: 44px;
		min-height: 44px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		cursor: pointer;
	}
</style>
