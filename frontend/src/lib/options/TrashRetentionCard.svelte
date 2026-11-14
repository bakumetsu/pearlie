<script lang="ts">
	import { untrack } from "svelte";
	import { options } from "../stores/options.svelte";
	import type { OptionsStore } from "../stores/options.svelte";
	import { getApi } from "../api/client";
	import type { Api } from "../api/client";

	let {
		store = options,
		api = getApi(),
	}: {
		store?: OptionsStore;
		api?: Api;
	} = $props();

	const current = $derived(store.values?.trash_retention_days ?? 7);

	let draft = $state<number | string>(untrack(() => current));
	let error: string = $state("");
	let dialogOpen = $state(false);
	let dialogDays = $state(0);
	let dialogCount = $state(0);

	let inputEl: HTMLInputElement | undefined = $state();
	let cancelBtn: HTMLButtonElement | undefined = $state();
	let deleteBtn: HTMLButtonElement | undefined = $state();
	let previouslyFocused: HTMLElement | null = $state(null);

	$effect(() => {
		if (error || dialogOpen) return;
		draft = current;
	});

	$effect(() => {
		if (dialogOpen) cancelBtn?.focus();
	});

	async function handleChange(e: Event) {
		const input = e.target as HTMLInputElement;
		const n = Number(input.value);
		if (!Number.isInteger(n) || n < 1 || n > 365) {
			error = "Enter a whole number from 1 to 365";
			input.value = String(current);
			draft = current;
			return;
		}
		error = "";
		if (n === current) return;
		if (n > current) {
			store.set({ trash_retention_days: n });
			return;
		}
		let count: number;
		try {
			const res = await api.purgePreview(n);
			count = res.count;
		} catch {
			error = "Could not check how many items would be deleted";
			input.value = String(current);
			draft = current;
			return;
		}
		if (count === 0) {
			store.set({ trash_retention_days: n });
			return;
		}
		dialogDays = n;
		dialogCount = count;
		previouslyFocused = document.activeElement as HTMLElement;
		dialogOpen = true;
	}

	function closeDialog() {
		dialogOpen = false;
		draft = current;
		if (inputEl) inputEl.value = String(current);
		if (previouslyFocused) previouslyFocused.focus();
	}

	function confirmDelete() {
		store.set({ trash_retention_days: dialogDays, confirm_purge: true });
		dialogOpen = false;
		if (previouslyFocused) previouslyFocused.focus();
	}

	function onDialogKeydown(e: KeyboardEvent) {
		if (e.key === "Escape") {
			e.preventDefault();
			closeDialog();
			return;
		}
		if (e.key === "Tab") {
			e.preventDefault();
			const focusable: HTMLElement[] = [];
			if (cancelBtn) focusable.push(cancelBtn);
			if (deleteBtn) focusable.push(deleteBtn);
			if (focusable.length === 0) return;
			const idx = focusable.indexOf(document.activeElement as HTMLElement);
			let next: number;
			if (e.shiftKey) {
				next = idx <= 0 ? focusable.length - 1 : idx - 1;
			} else {
				next = (idx + 1) % focusable.length;
			}
			focusable[next]?.focus();
		}
	}
</script>

<section class="card">
	<h2 class="card-title">Trash retention</h2>
	<p class="hint">Days to keep deleted items before they are removed</p>
	<div class="row">
		<label for="trash-retention-days">Retention days</label>
		<input
			id="trash-retention-days"
			type="number"
			inputmode="numeric"
			min={1}
			max={365}
			step={1}
			data-testid="trash-retention"
			aria-label="Retention days"
			bind:this={inputEl}
			value={draft}
			onchange={handleChange}
		/>
	</div>
	{#if error}<span class="err" role="alert">{error}</span>{/if}
</section>

{#if dialogOpen}
	<div class="overlay" role="presentation" onclick={(e) => { if (e.target === e.currentTarget) closeDialog(); }}>
		<div
			role="dialog"
			tabindex="-1"
			aria-modal="true"
			aria-labelledby="trash-dialog-title"
			aria-describedby="trash-dialog-desc"
			onkeydown={onDialogKeydown}
		>
			<h2 class="card-title" id="trash-dialog-title">
				Delete {dialogCount} item{dialogCount === 1 ? "" : "s"} now?
			</h2>
			<p id="trash-dialog-desc">
				Retention drops to {dialogDays} days. Demo trash items older than that
				are deleted immediately.
			</p>
			<div class="row">
				<button class="btn" bind:this={cancelBtn} onclick={closeDialog}>Cancel</button>
				<button class="btn primary" bind:this={deleteBtn} onclick={confirmDelete}>Delete</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.4);
		z-index: 1000;
	}

	.overlay > div[role="dialog"] {
		background: var(--surface);
		border-radius: 8px;
		padding: var(--s-4);
		max-width: 420px;
		width: calc(100% - 32px);
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
	}

	.overlay .btn {
		min-height: 44px;
		padding: 0 16px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		cursor: pointer;
		background: transparent;
		color: inherit;
		font-size: 0.9rem;
	}

	.overlay .btn.primary {
		background: var(--accent-bg);
		color: var(--accent);
		border-color: var(--accent-bg);
	}
</style>
