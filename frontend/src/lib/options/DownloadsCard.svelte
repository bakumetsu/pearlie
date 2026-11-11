<script lang="ts">
	import { untrack } from "svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";

	type SiteKey = "danbooru" | "gelbooru" | "rule34" | "nhentai";

	const SITES: { key: SiteKey; label: string }[] = [
		{ key: "danbooru", label: "Danbooru" },
		{ key: "gelbooru", label: "Gelbooru" },
		{ key: "rule34", label: "Rule34" },
		{ key: "nhentai", label: "nhentai" }
	];

	const FALLBACK: Record<SiteKey, number> = {
		danbooru: 1,
		gelbooru: 1,
		rule34: 1,
		nhentai: 2
	};

	type SiteField = {
		value: string | number;
		error: string | null;
	};

	let { store = options }: { store?: OptionsStore } = $props();

	function createFields(): Record<SiteKey, SiteField> {
		const v = store.values;
		return {
			danbooru: {
				value: v?.source_pace?.danbooru?.value ?? FALLBACK.danbooru,
				error: null
			},
			gelbooru: {
				value: v?.source_pace?.gelbooru?.value ?? FALLBACK.gelbooru,
				error: null
			},
			rule34: {
				value: v?.source_pace?.rule34?.value ?? FALLBACK.rule34,
				error: null
			},
			nhentai: {
				value: v?.source_pace?.nhentai?.value ?? FALLBACK.nhentai,
				error: null
			}
		};
	}

	let fields = $state<Record<SiteKey, SiteField>>(untrack(() => createFields()));

	const meta = $derived.by(() => {
		const v = store.values;
		const result = {} as Record<
			SiteKey,
			{ default: number; locked: boolean; backing_off: boolean }
		>;

		for (const { key } of SITES) {
			const entry = v?.source_pace?.[key];
			result[key] = {
				default: entry?.default ?? FALLBACK[key],
				locked: entry?.locked ?? false,
				backing_off: entry?.backing_off ?? false
			};
		}

		return result;
	});

	$effect(() => {
		const v = store.values;

		for (const { key } of SITES) {
			if (fields[key].error) continue;
			fields[key].value = v?.source_pace?.[key]?.value ?? FALLBACK[key];
		}
	});

	function handleChange(site: SiteKey, e: Event) {
		const input = e.target as HTMLInputElement;
		const raw = input.value;
		const n = Number(raw);
		const def = meta[site].default;

		if (!Number.isFinite(n) || n < def) {
			fields[site].error = `Minimum is ${def}s`;
			fields[site].value = raw;
			return;
		}

		fields[site].error = null;
		fields[site].value = n;
		store.set({ source_pace: { [site]: n } as Record<SiteKey, number> });
	}
</script>

<section class="card">
	<h2 class="card-title">Downloads</h2>
	<p class="hint">Seconds between requests, per site</p>

	{#each SITES as { key, label } (key)}
		<div class="row">
			<label class="row-label" for={`pace-${key}`}>{label}</label>
			<span class="muted">default {meta[key].default}s</span>
			<input
				id={`pace-${key}`}
				type="number"
				inputmode="decimal"
				min={meta[key].default}
				step="0.5"
				aria-label={`${label} seconds between requests`}
				data-testid={`pace-${key}`}
				disabled={meta[key].locked}
				value={fields[key].value}
				onchange={(e) => handleChange(key, e)}
			/>
			{#if meta[key].backing_off}
				<span class="chip" role="status">Backing off</span>
			{/if}
			{#if meta[key].locked}
				<span class="chip">set in .env</span>
			{/if}
			{#if fields[key].error}
				<span class="err" role="alert">Minimum is {meta[key].default}s</span>
			{/if}
		</div>
	{/each}
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
	.hint {
		margin: 0 0 var(--pad, 16px);
		font-size: 0.85rem;
		color: var(--muted, #999);
	}
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.5rem;
		min-height: 44px;
		margin-bottom: 0.5rem;
	}
	.row-label {
		font-size: 0.9rem;
	}
	.muted {
		font-size: 0.8rem;
		color: var(--muted, #999);
	}
	input[type="number"] {
		min-height: 44px;
		min-width: 44px;
		width: 5.5rem;
		padding: 0 0.5rem;
		border: 1px solid var(--border, #333);
		border-radius: 4px;
		background: var(--input-bg, #111);
		color: inherit;
		text-align: right;
	}
	input[type="number"]:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		min-height: 22px;
		padding: 0 0.5rem;
		border: 1px solid var(--muted, #555);
		border-radius: 999px;
		font-size: 0.7rem;
		color: var(--muted, #999);
	}
	.err {
		font-size: 0.8rem;
		color: var(--error, #ff6b6b);
	}
</style>
