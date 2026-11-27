<script lang="ts">
	import { onDestroy } from "svelte";
	import { connections } from "../stores/connections.svelte";
	import type { ConnectionsStore } from "../stores/connections.svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";
	import { getApi } from "../api/client";
	import type { Api } from "../api/client";
	import Icon from "../components/Icon.svelte";
	import type { IconName } from "../components/Icon.svelte";
	import ConnectionPopup from "./ConnectionPopup.svelte";

	type PillKind = "testing" | "rejected" | "down" | "backoff" | "ready" | "nokey" | "unknown";

	const SITES: { key: string; label: string }[] = [
		{ key: "danbooru", label: "Danbooru" },
		{ key: "gelbooru", label: "Gelbooru" },
		{ key: "rule34", label: "Rule34" },
		{ key: "nhentai", label: "nhentai" }
	];

	const PILLS: Record<PillKind, { text: string; icon: IconName }> = {
		testing: { text: "Testing", icon: "loader" },
		rejected: { text: "Key rejected", icon: "alert" },
		down: { text: "Down", icon: "alert" },
		backoff: { text: "Backing off", icon: "clock" },
		ready: { text: "Ready", icon: "check" },
		nokey: { text: "No key", icon: "minus" },
		unknown: { text: "Unknown", icon: "minus" }
	};

	const CONNECTED_MS = 4000;

	let {
		store = connections,
		optionsStore = options,
		api = getApi()
	}: {
		store?: ConnectionsStore;
		optionsStore?: OptionsStore;
		api?: Api;
	} = $props();

	let editing = $state<string | null>(null);
	let connected = $state<Record<string, boolean>>({});
	const timers: Record<string, ReturnType<typeof setTimeout>> = {};

	store.load(api);

	onDestroy(() => {
		for (const t of Object.values(timers)) clearTimeout(t);
	});

	// Display only: the table in design section 2.3, priority Testing, Key rejected, Down, Backing off, Ready, No key.
	function pillFor(key: string): PillKind {
		if (store.error) return "unknown";
		if (store.testing[key]) return "testing";
		const c = store.byName(key);
		if (key === "nhentai" && c?.key === "set" && c.auth === "failed") return "rejected";
		const result = store.results[key];
		if (result && !result.ok) return "down";
		if (optionsStore.values?.source_pace?.[key]?.backing_off) return "backoff";
		if (c?.key === "set" || result?.ok) return "ready";
		return "nokey";
	}

	function reasonFor(key: string): { text: string; link: string } | null {
		const kind = pillFor(key);
		if (kind === "rejected") {
			const blocked = store.byName(key)?.reason === "blocked";
			return { text: `nhentai ${blocked ? "blocked" : "rejected"} this key.`, link: "Edit key" };
		}
		if (kind === "down") return { text: store.results[key]?.message ?? "Test failed", link: "Edit settings" };
		if (kind === "backoff") {
			return { text: "The site said slow down. Pearlie waits longer between requests.", link: "Edit settings" };
		}
		if (connected[key]) return { text: "Connected", link: "" };
		return null;
	}

	async function runTest(key: string) {
		await store.test(api, key);
		if (!store.results[key]?.ok) return;
		clearTimeout(timers[key]);
		connected = { ...connected, [key]: true };
		timers[key] = setTimeout(() => {
			connected = { ...connected, [key]: false };
		}, CONNECTED_MS);
	}

	function editingLabel(): string {
		return SITES.find((s) => s.key === editing)?.label ?? "";
	}
</script>

<section class="card sites" aria-labelledby="sites-title">
	<h2 id="sites-title" class="card-title">Sites</h2>

	{#if store.error}
		<div class="load-error" role="alert">
			<span class="err">Could not load sites</span>
			<button class="btn" onclick={() => store.load(api)}>Retry</button>
		</div>
	{/if}

	<div class="shead" aria-hidden="true"><span>Status</span><span>Site</span><span></span><span></span></div>

	{#each SITES as { key, label } (key)}
		{@const kind = pillFor(key)}
		{@const reason = reasonFor(key)}
		{@const address = store.byName(key)?.address}
		<div class="srow" data-testid={`site-${key}`}>
			<span class="pill {kind}" role="status" aria-label={`${label} status: ${PILLS[kind].text}`}>
				<span class:spin={kind === "testing"}><Icon name={PILLS[kind].icon} size={14} /></span>
				{PILLS[kind].text}
			</span>
			<span class="site">
				<b>{label}</b>
				{#if address}<span class="muted url" title={address}>{address}</span>{/if}
			</span>
			<button
				class="btn ic"
				aria-label={`Test ${label}`}
				title="Test connection"
				disabled={store.testing[key]}
				onclick={() => runTest(key)}
			>
				<Icon name={store.testing[key] ? "loader" : "refresh"} size={18} />
			</button>
			<button class="btn ic" aria-label={`Edit ${label}`} title={`Edit ${label}`} onclick={() => (editing = key)}>
				<Icon name="settings" size={18} />
			</button>
			<div class="reason" aria-live="polite">
				{#if reason}
					{reason.text}
					{#if reason.link}
						<button class="link" onclick={() => (editing = key)}>{reason.link}</button>
					{/if}
				{/if}
			</div>
		</div>
	{/each}
</section>

{#if editing}
	<ConnectionPopup name={editing} label={editingLabel()} {store} {api} onclose={() => (editing = null)} />
{/if}

<style>
	.sites {
		container-type: inline-size;
	}
	.shead,
	.srow {
		display: grid;
		grid-template-columns: 96px 1fr 44px 44px;
		align-items: center;
		column-gap: 8px;
		margin: 0 16px;
	}
	.shead {
		padding: 6px 0 2px;
		font-size: var(--t-12);
		color: var(--muted);
	}
	.srow {
		min-height: 56px;
		padding: 6px 0;
		border-top: 1px solid #2c2c33;
		row-gap: 2px;
		font-size: var(--t-15);
	}
	.site {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.site b {
		font-size: var(--t-14);
		font-weight: 600;
	}
	.url {
		font-size: var(--t-12);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.reason {
		grid-column: 2 / -1;
		font-size: var(--t-13);
		color: var(--muted);
	}
	.reason:empty {
		display: none;
	}
	.link {
		min-height: 44px;
		padding: 0 6px;
		border: 0;
		background: transparent;
		color: var(--accent);
		font: inherit;
		cursor: pointer;
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		width: max-content;
		padding: 2px 8px;
		border-radius: 99px;
		background: var(--line);
		color: var(--muted);
		font-size: var(--t-12);
		white-space: nowrap;
	}
	.pill.ready {
		background: var(--ok-bg);
		color: var(--ok-fg);
	}
	.pill.rejected,
	.pill.down {
		background: var(--danger-bg);
		color: var(--danger-fg);
	}
	.pill.backoff {
		background: #4a3a1f;
		color: #ffd9a0;
	}
	.spin {
		display: inline-flex;
		animation: sites-spin 1s linear infinite;
	}
	@keyframes sites-spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spin {
			animation: none;
		}
	}
	.load-error {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		margin: 0 16px;
		padding: 6px 0;
	}
	/* Narrow card: two lines. Line 1 pill, name, Test, settings; line 2 the URL. The header stays for screen readers only. */
	@container (max-width: 639px) {
		.shead {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
		}
		.srow {
			grid-template-areas:
				"pill name test edit"
				". url url url"
				". reason reason reason";
		}
		.site {
			display: contents;
		}
		.site b {
			grid-area: name;
		}
		.url {
			grid-area: url;
		}
		.srow > :nth-child(1) {
			grid-area: pill;
		}
		.srow > :nth-child(3) {
			grid-area: test;
		}
		.srow > :nth-child(4) {
			grid-area: edit;
		}
		.reason {
			grid-area: reason;
		}
	}
</style>
