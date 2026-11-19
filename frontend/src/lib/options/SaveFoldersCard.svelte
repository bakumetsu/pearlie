<script lang="ts">
	import { onMount } from "svelte";
	import { getApi, ApiError, errorText } from "../api/client";
	import type { Api, Destinations } from "../api/client";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";
	import Icon from "../components/Icon.svelte";

	let { api = getApi(), store = options }: { api?: Api; store?: OptionsStore } = $props();

	const placeMode = $derived(store.values?.place_mode ?? "suggest");
	const scanWait = $derived(store.values?.stump_scan_wait_s ?? 10);
	const SCAN_STEP = 5;
	function stepScanWait(dir: 1 | -1) {
		const n = dir > 0 ? Math.floor(scanWait / SCAN_STEP + 1) : Math.ceil(scanWait / SCAN_STEP - 1);
		store.set({ stump_scan_wait_s: Math.min(120, Math.max(0, n * SCAN_STEP)) });
	}

	let dest = $state<Destinations | null>(null);
	let loadError = $state("");
	let drafts: Record<string, string> = $state({});
	let errors: Record<string, string> = $state({});
	let saved: Record<string, boolean> = $state({});

	const DEFAULT_KEY = "default";

	const sites = $derived(dest?.sites ?? []);
	const paths = $derived(dest?.library_paths ?? []);
	const stumpSites = $derived(dest?.stump_sites ?? []);
	const stumpPaths = $derived(dest?.stump_library_paths ?? []);

	function adopt(d: Destinations) {
		dest = d;
		const next: Record<string, string> = { [DEFAULT_KEY]: d.default_folder };
		for (const site of [...(d.sites ?? []), ...(d.stump_sites ?? [])]) {
			next[site] = d.items.find((i) => i.site === site)?.folder ?? "";
		}
		drafts = next;
	}

	onMount(async () => {
		try {
			adopt(await api.getDestinations());
		} catch (e) {
			loadError = errorText(e);
		}
	});

	function message(e: unknown): string {
		if (e instanceof ApiError && e.status > 0 && e.message) return e.message;
		return errorText(e);
	}

	async function save(key: string) {
		const folder = (drafts[key] ?? "").trim();
		errors[key] = "";
		saved[key] = false;
		try {
			if (key === DEFAULT_KEY) {
				adopt(await api.putDefaultFolder(folder));
			} else if (folder === "") {
				if (dest?.items.some((i) => i.site === key)) adopt(await api.deleteSiteFolder(key));
			} else {
				adopt(await api.putSiteFolder(key, folder));
			}
			saved[key] = true;
		} catch (e) {
			errors[key] = message(e);
		}
	}

	// Library paths are Stash-side; folders are stored Pearlie-side, so map back.
	function toPearlie(path: string): string | null {
		const pp = dest?.prefix_pearlie ?? "";
		const ps = dest?.prefix_stash ?? "";
		if (!pp) return path;
		if (path === ps) return pp;
		if (path.startsWith(ps + "/")) return pp + path.slice(ps.length);
		return null;
	}

	const pickable = $derived(
		paths.map((p) => toPearlie(p)).filter((p): p is string => p !== null),
	);

	function pathsFor(key: string): string[] {
		return stumpSites.includes(key) ? stumpPaths : pickable;
	}

	function pick(key: string, path: string) {
		drafts[key] = path;
	}

	let mapPearlie = $state("");
	let mapStash = $state("");
	let mapError = $state("");

	$effect(() => {
		mapPearlie = dest?.prefix_pearlie ?? "";
		mapStash = dest?.prefix_stash ?? "";
	});

	async function saveMapping() {
		mapError = "";
		try {
			adopt(await api.putPathMapping(mapPearlie.trim(), mapStash.trim()));
		} catch (e) {
			mapError = message(e);
		}
	}

	async function resetMapping() {
		mapError = "";
		try {
			adopt(await api.resetPathMapping());
		} catch (e) {
			mapError = message(e);
		}
	}
</script>

<section class="card" id="save-folders" data-testid="save-folders">
	<h2 class="card-title">Save folders</h2>
	<p class="hint">Where saved posts go. Folders must be inside a Stash library path (Stump sites: a Stump library root).</p>
	{#if loadError}
		<span class="err" role="alert">{loadError}</span>
	{:else if dest}
		{#if dest.stump_library_error}
			<p class="hint" role="status">Could not read Stump libraries: {dest.stump_library_error}</p>
		{/if}
		{#if dest.library_error}
			<p class="hint" role="status">Could not read Stash library paths: {dest.library_error}</p>
		{:else if paths.length}
			<p class="hint">Stash library paths</p>
			<ul class="paths" data-testid="library-paths">
				{#each paths as path (path)}
					<li><code>{path}</code></li>
				{/each}
			</ul>
		{/if}
		<form
			class="row folder-row"
			data-testid="mapping"
			onsubmit={(e) => {
				e.preventDefault();
				saveMapping();
			}}
		>
			<label for="map-pearlie">Path mapping</label>
			<input id="map-pearlie" type="text" data-testid="map-pearlie" placeholder="Pearlie path" autocomplete="off" bind:value={mapPearlie} />
			<input id="map-stash" type="text" data-testid="map-stash" aria-label="Stash path" placeholder="Stash path" autocomplete="off" bind:value={mapStash} />
			<button class="btn" type="submit" data-testid="save-mapping">Save</button>
			{#if !dest.prefix_from_env}
				<button class="btn" type="button" data-testid="reset-mapping" onclick={resetMapping}>Reset to .env</button>
			{/if}
			<span class="ok" data-testid="mapping-source">{dest.prefix_from_env ? "From .env" : "Saved here"}</span>
			{#if mapError}<span class="err" role="alert">{mapError}</span>{/if}
		</form>
		{#each [DEFAULT_KEY, ...sites, ...stumpSites] as key (key)}
			<form
				class="row folder-row"
				onsubmit={(e) => {
					e.preventDefault();
					save(key);
				}}
			>
				<label for="folder-{key}">{key === DEFAULT_KEY ? "Default folder" : key}</label>
				<input
					id="folder-{key}"
					type="text"
					data-testid="folder-{key}"
					placeholder={key === DEFAULT_KEY
						? ""
						: stumpSites.includes(key)
							? "Stump folder"
							: "Uses the default"}
					autocomplete="off"
					spellcheck="false"
					bind:value={drafts[key]}
					oninput={() => {
						saved[key] = false;
					}}
				/>
				<button class="btn" type="submit" data-testid="save-{key}">Save</button>
				{#if pathsFor(key).length}
					<select
						aria-label="Pick a library path for {key}"
						data-testid="pick-{key}"
						onchange={(e) => {
							pick(key, e.currentTarget.value);
							e.currentTarget.value = "";
						}}
					>
						<option value="">Library paths</option>
						{#each pathsFor(key) as path (path)}
							<option value={path}>{path}</option>
						{/each}
					</select>
				{/if}
				{#if errors[key]}<span class="err" role="alert">{errors[key]}</span>{/if}
				{#if saved[key]}<span class="ok" role="status">Saved</span>{/if}
			</form>
		{/each}
		{#if stumpSites.length}
			<div class="row place-row" data-testid="place-mode">
				<span id="place-label">Stump placement</span>
				<div class="seg" role="radiogroup" aria-labelledby="place-label">
					<button
						type="button"
						role="radio"
						aria-checked={placeMode === "auto"}
						data-testid="place-auto"
						class:on={placeMode === "auto"}
						onclick={() => store.set({ place_mode: "auto" })}
					>
						<Icon name="wand-sparkles" size={18} /><span>Auto</span>
					</button>
					<button
						type="button"
						role="radio"
						aria-checked={placeMode === "suggest"}
						data-testid="place-suggest"
						class:on={placeMode === "suggest"}
						onclick={() => store.set({ place_mode: "suggest" })}
					>
						<Icon name="mouse-pointer" size={18} /><span>Suggest</span>
					</button>
				</div>
				<span class="ok" data-testid="place-hint">
					{placeMode === "auto"
						? "Pearlie picks series or oneshot alone."
						: "The save dialog shows the pick; one tap changes it."}
				</span>
				<span class="ok" data-testid="oneshots-line">
					{dest.stump_oneshots_dir
						? `Oneshots: ${dest.stump_oneshots_dir}`
						: "Oneshots: not set in Stump"}
				</span>
				{#if dest.stump_oneshots_dir}
					<span class="ok" data-testid="oneshots-note">
						A first book moves into a new series. Stump keeps read progress only if "Hash files" is on.
					</span>
				{/if}
			</div>
			<div class="row scan-row" data-testid="scan-wait">
				<span id="scan-wait-label"><Icon name="clock" size={18} /> Stump scan delay</span>
				<div class="stepper" role="group" aria-labelledby="scan-wait-label">
					<button
						type="button"
						aria-label="Shorter delay"
						data-testid="scan-wait-minus"
						disabled={scanWait <= 0}
						onclick={() => stepScanWait(-1)}
					>
						<Icon name="minus" size={18} />
					</button>
					<output data-testid="scan-wait-value">{scanWait} s</output>
					<button
						type="button"
						aria-label="Longer delay"
						data-testid="scan-wait-plus"
						disabled={scanWait >= 120}
						onclick={() => stepScanWait(1)}
					>
						<Icon name="plus" size={18} />
					</button>
				</div>
				<span class="ok">Wait this long after the last save before Stump scans.</span>
			</div>
		{/if}
	{/if}
</section>

<style>
	.paths {
		list-style: none;
		margin: 0;
		padding: 0 16px 8px;
		font-size: var(--t-13);
		color: var(--muted);
	}

	.folder-row input[type="text"] {
		flex: 1 1 220px;
		min-width: 0;
		min-height: 44px;
		padding: 0 10px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		font: inherit;
	}

	.folder-row .btn,
	.folder-row select {
		min-height: 44px;
		padding: 0 14px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		font: inherit;
		cursor: pointer;
	}

	.folder-row select {
		max-width: 160px;
	}

	.stepper {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.stepper button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 44px;
		min-height: 44px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		cursor: pointer;
	}

	.stepper button:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.stepper output {
		min-width: 48px;
		text-align: center;
	}

	.seg {
		display: flex;
		gap: 8px;
	}

	.seg button {
		display: inline-flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		min-width: 64px;
		min-height: 44px;
		padding: 4px 12px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		font-size: var(--t-13);
		cursor: pointer;
	}

	.seg button.on {
		background: var(--accent-bg);
		color: var(--accent);
	}

	.ok {
		flex-basis: 100%;
		color: var(--muted);
		font-size: var(--t-13);
	}
</style>
