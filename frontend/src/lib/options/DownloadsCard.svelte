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

	const MAX_PACE = 3600;

	// Shown only until the first GET lands; mirrors throttle.DEFAULT_PACE in the backend.
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
		if (n > MAX_PACE) {
			fields[site].error = `Maximum is ${MAX_PACE}s`;
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
				max={MAX_PACE}
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
				<span class="err" role="alert">{fields[key].error}</span>
			{/if}
		</div>
	{/each}
</section>
