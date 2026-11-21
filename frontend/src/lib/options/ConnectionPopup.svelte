<script lang="ts">
	import { untrack } from "svelte";
	import { connections } from "../stores/connections.svelte";
	import type { ConnectionsStore } from "../stores/connections.svelte";
	import { getApi, ApiError, errorText } from "../api/client";
	import Icon from "../components/Icon.svelte";
	import type { Api } from "../api/client";

	let {
		name,
		label,
		store = connections,
		api = getApi(),
		onclose
	}: {
		name: string;
		label: string;
		store?: ConnectionsStore;
		api?: Api;
		onclose: () => void;
	} = $props();

	const conn = $derived(store.byName(name));

	const showAddress = $derived(!conn?.address_fixed);
	const addressLocked = $derived(!!conn?.address_locked);
	const keyLocked = $derived(!!conn?.key_locked);
	const keySet = $derived(conn?.key === "set");
	// Sites with more than one credential field (login + key, cookie + User-Agent, ...)
	const fields = $derived(conn?.fields ?? []);
	const multi = $derived(fields.length > 1);
	// nhentai: the API key is the main field; Cookie and User-Agent sit under "Advanced"
	const hasApiKey = $derived(name === "nhentai" && fields.some((f) => f.id === "api_key"));
	const mainFields = $derived(hasApiKey ? fields.filter((f) => f.id === "api_key") : fields);
	const advFields = $derived(hasApiKey ? fields.filter((f) => f.id !== "api_key") : []);
	let advOpen = $state(untrack(() => (store.byName(name)?.fields ?? []).some((f) => f.id === "cookie" && f.state === "set")));
	const NHENTAI_KEY_URL = "https://nhentai.net/user/settings";
	const keyRejected = $derived(hasApiKey && conn?.auth === "failed");
	const keyRejectedText = $derived(
		conn?.reason === "blocked" ? "nhentai blocked this key" : "nhentai rejected this key"
	);
	function chipText(f: { id: string; state: string }): string {
		if (f.id !== "api_key" || f.state !== "set") return f.state;
		if (conn?.auth === "ok") return "ok";
		if (conn?.auth === "failed") return "invalid";
		return f.state;
	}
	const canEditKeys = $derived(store.canStore);
	// Fixed length: neither the real key nor its length reaches the DOM
	const MASK = "•".repeat(8);

	let address = $state(untrack(() => store.byName(name)?.address ?? ""));
	let key = $state("");
	let values = $state<Record<string, string>>({});
	let busy = $state(false);
	let error = $state<string | null>(null);
	// Fields the user edited; a touched, empty secret field means "remove"
	let touched = $state<Record<string, boolean>>({});

	const clearKey = $derived(
		keySet && !keyLocked && canEditKeys && !!touched.key && !key.trim()
	);
	const clearFieldIds = $derived(
		fields
			.filter(
				(f) =>
					f.state === "set" &&
					!f.locked &&
					canEditKeys &&
					touched[f.id] &&
					!(values[f.id] ?? "").trim()
			)
			.map((f) => f.id)
	);

	const normalizedAddress = $derived(address.trim().replace(/\/$/, ""));
	const originalAddress = $derived(
		(conn?.address ?? "").trim().replace(/\/$/, "")
	);
	const addressChanged = $derived(
		showAddress && !addressLocked && normalizedAddress !== originalAddress
	);

	let addrInput: HTMLInputElement | undefined = $state();
	let keyInput: HTMLInputElement | undefined = $state();
	let dialogEl: HTMLDivElement | undefined = $state();

	const prevFocused = untrack(() =>
		document.activeElement instanceof HTMLElement
			? document.activeElement
			: null
	);

	$effect(() => {
		if (showAddress && !addressLocked) {
			addrInput?.focus();
		} else if (!keyLocked && store.canStore) {
			keyInput?.focus();
		} else {
			dialogEl?.querySelector<HTMLElement>("button:not([disabled])")?.focus();
		}
	});

	$effect(() => {
		return () => {
			prevFocused?.focus();
		};
	});

	function handleOverlayClick(e: MouseEvent) {
		if (e.target === e.currentTarget) onclose();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === "Escape") {
			e.preventDefault();
			onclose();
			return;
		}
		if (e.key === "Tab" && dialogEl) {
			const focusables = dialogEl.querySelectorAll<HTMLElement>(
				'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
			);
			if (focusables.length === 0) return;
			const first = focusables[0];
			const last = focusables[focusables.length - 1];
			if (e.shiftKey) {
				if (document.activeElement === first) {
					e.preventDefault();
					last.focus();
				}
			} else {
				if (document.activeElement === last) {
					e.preventDefault();
					first.focus();
				}
			}
		}
	}

	async function handleSaveAndTest() {
		busy = true;
		error = null;

		const body: Record<string, unknown> = {};
		if (addressChanged) {
			body.address = normalizedAddress;
		}
		if (key.trim()) {
			body.secret = key.trim();
		} else if (clearKey && !multi) {
			body.clear_secret = true;
		}
		const typed = Object.fromEntries(
			Object.entries(values)
				.map(([id, v]) => [id, v.trim()])
				.filter(([, v]) => v)
		);
		if (Object.keys(typed).length > 0) {
			body.fields = typed;
		}
		if (multi && clearFieldIds.length > 0) {
			body.clear_fields = clearFieldIds;
		}

		try {
			if (Object.keys(body).length > 0) {
				await store.save(api, name, body);
			}
			key = "";
			values = {};
			touched = {};
			await store.test(api, name);
			// A rejected key stays visible in the popup so the user need not press Test
			if (hasApiKey && store.results[name] && !store.results[name]!.ok) return;
			onclose();
		} catch (e) {
			if (e instanceof ApiError) {
				error = errorText(e);
			} else {
				throw e;
			}
		} finally {
			busy = false;
		}
	}
</script>

<div class="overlay" onclick={handleOverlayClick}>
	<div
		class="dialog"
		role="dialog"
		aria-modal="true"
		aria-labelledby="conn-popup-title"
		bind:this={dialogEl}
		onkeydown={handleKeydown}
	>
		<h2 id="conn-popup-title" class="card-title">Edit {label}</h2>

		{#if showAddress}
			<div class="row">
				<label for="conn-addr">Address</label>
				<input
					id="conn-addr"
					type="url"
					bind:this={addrInput}
					bind:value={address}
					disabled={addressLocked}
				/>
				{#if addressLocked}
					<span class="chip">set in .env</span>
				{/if}
				{#if addressChanged}
					<p class="hint">Changing the address clears the stored key unless you also enter a key.</p>
				{/if}
			</div>
		{/if}

		{#if multi}
			{#each mainFields as f (f.id)}
				<div class="row">
					<label for={`conn-f-${f.id}`}>{f.label}</label>
					<input
						id={`conn-f-${f.id}`}
						type={f.primary ? "password" : "text"}
						autocomplete="off"
						value={values[f.id] ?? ""}
						oninput={(e) => {
							values = { ...values, [f.id]: e.currentTarget.value };
							touched = { ...touched, [f.id]: true };
						}}
						placeholder={f.state === "set" && !touched[f.id] ? MASK : ""}
						aria-describedby={f.id === "api_key" && keyRejected ? "conn-key-err" : undefined}
						disabled={f.locked || !canEditKeys}
					/>
					{#if f.locked}
						<span class="chip">set in .env</span>
					{:else}
						<span class="chip" class:ok={chipText(f) === "ok"} class:bad={chipText(f) === "invalid"}>{chipText(f)}</span>
					{/if}
					{#if clearFieldIds.includes(f.id)}
						<p class="hint">{f.label} will be removed</p>
					{/if}
				</div>
			{/each}
			{#if hasApiKey}
				{#if keyRejected}
					<p class="err" id="conn-key-err" role="alert">{keyRejectedText}</p>
				{/if}
				<div class="row">
					<span class="hint grow-hint">Create it in nhentai Settings &gt; API keys</span>
					<a
						class="btn"
						href={NHENTAI_KEY_URL}
						target="_blank"
						rel="noopener noreferrer"
						aria-label="Open nhentai API key settings (new tab)"><Icon name="external-link" size={16} /></a
					>
				</div>
				{#if advOpen}
					<div id="conn-advanced">
						{#each advFields as f (f.id)}
							<div class="row">
								<label for={`conn-f-${f.id}`}>{f.label}</label>
								<input
									id={`conn-f-${f.id}`}
									type={f.id === "cookie" ? "password" : "text"}
									autocomplete="off"
									value={values[f.id] ?? ""}
									oninput={(e) => {
										values = { ...values, [f.id]: e.currentTarget.value };
										touched = { ...touched, [f.id]: true };
									}}
									placeholder={f.state === "set" && !touched[f.id] ? MASK : ""}
									disabled={f.locked || !canEditKeys}
								/>
								{#if f.locked}
									<span class="chip">set in .env</span>
								{:else}
									<span class="chip">{f.state}</span>
								{/if}
								{#if clearFieldIds.includes(f.id)}
									<p class="hint">{f.label} will be removed</p>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			{/if}
			{#if !store.canStore}
				<p class="note" role="note">Keys can't be saved here: Pearlie could not create its encryption key file. Check that the data folder is writable, or set PEARLIE_SECRET_KEY in .env.</p>
			{/if}
		{:else}
		<div class="row">
			<label for="conn-key">Key</label>
			<input
				id="conn-key"
				type="password"
				autocomplete="off"
				bind:this={keyInput}
				bind:value={key}
				oninput={() => (touched = { ...touched, key: true })}
				placeholder={(keySet || keyLocked) && !touched.key ? MASK : ""}
				disabled={keyLocked || !store.canStore}
			/>
			{#if keyLocked}
				<span class="chip">set in .env</span>
			{:else}
				<span class="chip">{keySet ? "set" : "missing"}</span>
			{/if}
			{#if !store.canStore}
				<p class="note" role="note">Keys can't be saved here: Pearlie could not create its encryption key file. Check that the data folder is writable, or set PEARLIE_SECRET_KEY in .env.</p>
			{/if}
		</div>

		{#if clearKey}
			<p class="hint">Key will be removed</p>
		{/if}

		{/if}

		{#if error}
			<p class="err" role="alert">{error}</p>
		{/if}

		<div class="row actions">
			{#if multi && hasApiKey}
				<button
					class="btn fold"
					type="button"
					aria-expanded={advOpen}
					aria-controls="conn-advanced"
					onclick={() => (advOpen = !advOpen)}
				>
					<Icon name={advOpen ? "chevron-down" : "chevron-right"} size={16} /> Advanced
				</button>
			{/if}
			<button class="btn" disabled={busy} onclick={onclose}>Cancel</button>
			<button class="btn primary" disabled={busy} onclick={handleSaveAndTest}>Save</button>
		</div>
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.55);
		backdrop-filter: blur(6px);
		z-index: 1000;
	}
	.dialog {
		background: var(--bg, #1a1a1a);
		border: 1px solid var(--border, #333);
		border-radius: var(--radius, 8px);
		padding: var(--pad, 16px);
		min-width: 280px;
		max-width: 440px;
		width: 90%;
	}
	.card-title {
		margin: 0 0 var(--pad, 16px);
		font-size: 1.1rem;
	}
	.row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		min-height: 44px;
		margin-bottom: 0.5rem;
	}
	.row label {
		font-size: 0.9rem;
		min-width: 4rem;
	}
	.row input {
		min-height: 44px;
		flex: 1;
		padding: 0 0.5rem;
		border: 1px solid var(--border, #333);
		border-radius: 4px;
		background: var(--input-bg, #111);
		color: inherit;
	}
	.row input:disabled {
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
	.chip.ok {
		background: var(--ok-bg);
		color: var(--ok-fg);
		border-color: transparent;
	}
	.chip.bad {
		color: var(--danger-hot, #ff6b6b);
		border-color: var(--danger-hot, #ff6b6b);
	}
	.grow-hint {
		flex: 1;
	}
	a.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: inherit;
		text-decoration: none;
	}
	.fold {
		margin-right: auto;
		justify-content: flex-start;
		gap: 0.25rem;
		padding: 0 0.25rem;
		border: 0;
		background: transparent;
	}
	.hint {
		width: 100%;
		margin: 0;
		font-size: 0.8rem;
		color: var(--muted, #999);
	}
	.note {
		width: 100%;
		margin: 0;
		font-size: 0.8rem;
		color: var(--muted, #999);
	}
	.err {
		font-size: 0.8rem;
		color: var(--error, #ff6b6b);
	}
	.btn {
		min-height: 44px;
		min-width: 44px;
		padding: 0 1rem;
		border: 1px solid var(--border, #333);
		border-radius: 4px;
		background: var(--input-bg, #111);
		color: inherit;
		cursor: pointer;
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.btn.primary {
		background: var(--primary, #4466cc);
		border-color: var(--primary, #4466cc);
		color: #fff;
	}
	.actions {
		justify-content: flex-end;
		margin-top: var(--pad, 16px);
	}
</style>
