<script lang="ts">
	import { untrack } from "svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";
	import { getApi } from "../api/client";
	import type { Api } from "../api/client";
	import Icon from "../components/Icon.svelte";
	import NumberStepper from "./NumberStepper.svelte";

	let { store = options, api = getApi() }: { store?: OptionsStore; api?: Api } = $props();

	const cache = $derived(store.values?.thumb_cache);
	const currentCap = $derived(cache?.max_mb ?? 1024);
	let draft = $state<number | string>(untrack(() => currentCap));
	let capError = $state("");

	let clearedAt = $state<{ used: number; files: number } | null>(null);
	const cleared = $derived(
		clearedAt !== null &&
			cache?.used_mb === clearedAt.used &&
			cache?.files === clearedAt.files
	);
	const effectiveUsed = $derived(cleared ? 0 : (cache?.used_mb ?? 0));
	const effectiveFiles = $derived(cleared ? 0 : (cache?.files ?? 0));

	const usedText = $derived(formatSize(effectiveUsed));
	const capText = $derived(formatSize(currentCap));
	const capGbText = $derived(formatGB(currentCap));
	const percent = $derived(
		currentCap > 0 ? Math.min(100, Math.max(0, (effectiveUsed / currentCap) * 100)) : 0
	);
	const nearLimit = $derived(currentCap > 0 && effectiveUsed / currentCap >= 0.9);

	const isClearDisabled = $derived(
		!cache?.available || (effectiveUsed === 0 && effectiveFiles === 0)
	);
	const clearTitleAttr = $derived(
		!cache?.available ? "Cache unavailable" : (effectiveUsed === 0 && effectiveFiles === 0 ? "Cache is empty" : "")
	);

	let confirming = $state(false);
	let busy = $state(false);
	let confirmTimer: ReturnType<typeof setTimeout> | undefined;
	let clearError = $state("");

	$effect(() => { if (capError) return; draft = currentCap; });

	$effect(() => {
		return () => {
			if (confirmTimer) {
				clearTimeout(confirmTimer);
				confirmTimer = undefined;
			}
		};
	});

	function formatSize(mb: number): string {
		if (mb < 1024) {
			return `${parseFloat(mb.toFixed(1))} MB`;
		}
		return formatGB(mb);
	}

	function formatGB(mb: number): string {
		return `${parseFloat((mb / 1024).toFixed(2))} GB`;
	}

	function handleCapChange(e: Event) {
		const input = e.target as HTMLInputElement;
		const raw = input.value;
		if (!/^\d+$/.test(raw) || Number(raw) < 50 || Number(raw) > 20480) {
			capError = "Enter a whole number from 50 to 20480";
			input.value = String(currentCap);
			draft = currentCap;
			return;
		}
		const n = Number(raw);
		capError = "";
		if (n === currentCap) return;
		store.set({ thumb_cache_max_mb: n });
		draft = n;
	}

	function cancelConfirm() {
		confirming = false;
		if (confirmTimer) {
			clearTimeout(confirmTimer);
			confirmTimer = undefined;
		}
	}

	async function handleClear() {
		if (busy) return;
		if (confirming) {
			cancelConfirm();
			busy = true;
			try {
				await api.clearThumbCache();
				clearedAt = { used: cache?.used_mb ?? 0, files: cache?.files ?? 0 };
				clearError = "";
			} catch {
				clearError = "Could not clear the cache";
			} finally {
				busy = false;
			}
			return;
		}
		confirming = true;
		clearError = "";
		confirmTimer = setTimeout(() => {
			confirmTimer = undefined;
			confirming = false;
		}, 4000);
	}

	function handleClearKeydown(e: KeyboardEvent) {
		if (e.key === "Escape") {
			cancelConfirm();
		}
	}

	function handleClearBlur() {
		cancelConfirm();
	}
</script>

<section class="card">
	<h2 class="card-title">Thumbnail cache</h2>
	{#if store.values === null}
		<p class="hint">Loading…</p>
	{:else}
		<div class="row">
			<Icon name="image" />
			<span>{usedText} of {capText} used</span>
			<div class="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}>
				<div class="fill" style="width:{percent}%"></div>
			</div>
			{#if nearLimit}<span class="badge">Near the limit</span>{/if}
		</div>
		<div class="row controls">
			<div class="cap-group">
				<label for="thumb-cache-cap">Size limit (MB)</label>
				<NumberStepper label="size limit">
					<input
						id="thumb-cache-cap"
						type="number"
						inputmode="numeric"
						min={50}
						max={20480}
						step={1}
						data-testid="thumb-cache-cap"
						aria-label="Size limit in MB"
						value={draft}
						onchange={handleCapChange}
					/>
				</NumberStepper>
				<span class="helper">{capGbText}</span>
			</div>
			<button
				type="button"
				class="clear"
				data-testid="thumb-cache-clear"
				aria-label={confirming ? "Tap again to clear" : "Clear thumbnail cache"}
				disabled={isClearDisabled || busy}
				title={clearTitleAttr || undefined}
				onclick={handleClear}
				onkeydown={handleClearKeydown}
				onblur={handleClearBlur}
			>
				<Icon name="trash" />
				{#if confirming}<span>Tap again to clear</span>{/if}
			</button>
		</div>
		{#if capError}<span class="err" role="alert">{capError}</span>{/if}
		{#if clearError}<span class="err" role="alert">{clearError}</span>{/if}
	{/if}
</section>

<style>
	.bar {
		height: 6px;
		background: var(--line-strong);
		border-radius: 3px;
		overflow: hidden;
	}
	.fill {
		height: 100%;
		background: var(--accent);
	}
	.badge {
		font-size: 0.75rem;
		padding: 2px 8px;
		border-radius: 999px;
		background: var(--accent);
		color: #fff;
	}
	input,
	.clear {
		min-height: 44px;
	}
	.clear {
		min-width: 44px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		cursor: pointer;
	}
	.controls {
		flex-wrap: wrap;
	}
	@media (min-width: 720px) {
		.controls {
			justify-content: space-between;
		}
	}
</style>
