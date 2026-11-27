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

	function createFields(): Record<SiteKey, SiteField> {
		const v = store.values;
		const out = {} as Record<SiteKey, SiteField>;
		for (const { key } of SITES) {
			out[key] = { value: v?.source_pace?.[key]?.value ?? FALLBACK[key], error: null };
		}
		return out;
	}

	let fields = $state<Record<SiteKey, SiteField>>(untrack(() => createFields()));

	const meta = $derived.by(() => {
		const v = store.values;
		const result = {} as Record<SiteKey, { default: number; locked: boolean }>;
		for (const { key } of SITES) {
			const entry = v?.source_pace?.[key];
			result[key] = { default: entry?.default ?? FALLBACK[key], locked: entry?.locked ?? false };
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

	function handlePace(site: SiteKey, e: Event) {
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

	<div class="delay" role="group" aria-labelledby="delay-title">
		<h3 id="delay-title" class="delay-title">Delay between requests</h3>
		<p class="hint">Seconds Pearlie waits between two requests to a site. A site that says slow down gets more.</p>
		{#each SITES as { key, label } (key)}
			<div class="delay-line">
				<label class="delay-name" for={`pace-${key}`}>{label}</label>
				{#if meta[key].locked}<span class="chip">set in .env</span>{/if}
				{#if fields[key].error}<span class="err" role="alert">{fields[key].error}</span>{/if}
				<span class="delay-field">
					<input
						id={`pace-${key}`}
						type="number"
						inputmode="decimal"
						min={meta[key].default}
						max={MAX_PACE}
						step="0.5"
						aria-label={`${label} seconds between requests`}
						title={`Seconds between requests. Default ${meta[key].default}s`}
						data-testid={`pace-${key}`}
						disabled={meta[key].locked}
						value={fields[key].value}
						onchange={(e) => handlePace(key, e)}
					/>
					<span class="muted" aria-hidden="true">s</span>
				</span>
			</div>
		{/each}
	</div>
</section>

<style>
	.delay-title {
		margin: 0;
		padding: 16px 16px 2px;
		border-top: 1px solid #2c2c33;
		font-size: var(--t-15);
		font-weight: 400;
	}
	.delay-line {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		min-height: 60px;
		margin: 0 16px;
		padding: 8px 0;
	}
	.delay-line + .delay-line {
		border-top: 1px solid #2c2c33;
	}
	.delay-name {
		flex: 1;
		min-width: 0;
		padding-left: 16px;
		font-size: var(--t-15);
	}
	.delay-field {
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}
	.delay-field :global(input[type="number"]) {
		width: 56px;
		padding: 0 8px;
		text-align: center;
	}
</style>
