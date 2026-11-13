<script lang="ts">
	import { untrack } from "svelte";
	import { connections } from "../stores/connections.svelte";
	import type { ConnectionsStore } from "../stores/connections.svelte";
	import { getApi, ApiError, errorText } from "../api/client";
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

<div class="overlay" on:click={handleOverlayClick}>
	<div
		class="dialog"
		role="dialog"
		aria-modal="true"
		aria-labelledby="conn-popup-title"
		bind:this={dialogEl}
		on:keydown={handleKeydown}
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
			{#each fields as f (f.id)}
				<div class="row">
					<label for={`conn-f-${f.id}`}>{f.label}</label>
					<input
						id={`conn-f-${f.id}`}
						type={f.primary ? "password" : "text"}
						autocomplete="off"
						value={values[f.id] ?? ""}
						on:input={(e) => {
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
				on:input={() => (touched = { ...touched, key: true })}
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
			<button class="btn" disabled={busy} on:click={onclose}>Cancel</button>
			<button class="btn primary" disabled={busy} on:click={handleSaveAndTest}>Save</button>
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

	@media (max-width: 768px) {
		.overlay {
			align-items: flex-end;
		}
		.dialog {
			width: 100%;
			max-width: none;
			border-radius: var(--radius, 8px) var(--radius, 8px) 0 0;
		}
	}
</style>
