<script lang="ts">
	import { onDestroy, onMount, tick } from "svelte";
	import { getApi } from "../api/client";
	import type { CreatedDebugKey as Created, DebugKeyStatus as Status, DebugKeyTtl as Ttl } from "../api/client";
	import Icon from "../components/Icon.svelte";
	import { toasts } from "../stores/toasts.svelte";

	const api = getApi();
	const TTLS: { id: Ttl; label: string }[] = [
		{ id: "1h", label: "1 hour" },
		{ id: "24h", label: "24 hours" },
		{ id: "7d", label: "7 days" },
		{ id: "never", label: "Never" },
	];

	let status = $state<Status | null>(null);
	let phase = $state<"loading" | "ready" | "error">("loading");
	let ttl = $state<Ttl>("24h");
	let busy = $state(false);
	// "pick": choose the lifetime; "shown": the new key, once. Both live in the dialog.
	let dialog = $state<"pick" | "shown" | null>(null);
	let dialogEl = $state<HTMLElement | null>(null);
	let opener: HTMLElement | null = null;
	// The key lives only here: never in storage, a log or the URL.
	let created = $state<Created | null>(null);
	let copied = $state(false);
	let keyBox = $state<HTMLElement | null>(null);
	let alive = true;
	let copiedTimer: ReturnType<typeof setTimeout> | undefined;
	onDestroy(() => {
		alive = false;
		created = null;
		clearTimeout(copiedTimer);
	});

	async function load() {
		phase = "loading";
		try {
			const s = await api.getDebugKey();
			if (!alive) return;
			status = s;
			phase = "ready";
		} catch {
			if (!alive) return;
			phase = "error";
		}
	}

	function rel(iso: string | null, future: boolean): string {
		if (!iso) return "never";
		const ms = new Date(iso).getTime() - Date.now();
		const mins = Math.round(Math.abs(ms) / 60000);
		let span: string;
		if (mins < 1) span = "under 1 min";
		else if (mins < 60) span = `${mins} min`;
		else if (mins < 60 * 48) span = `${Math.round(mins / 60)} h`;
		else span = `${Math.round(mins / 1440)} days`;
		return ms >= 0 && future ? `in ${span}` : `${span} ago`;
	}
	function exact(iso: string | null): string {
		return iso ? new Date(iso).toLocaleString() : "";
	}

	async function create() {
		if (busy) return;
		busy = true;
		try {
			const k = await api.createDebugKey(ttl);
			if (!alive) return;
			created = k;
			dialog = "shown";
			copied = false;
			await load();
		} catch {
			toasts.push({ kind: "error", message: "Could not create the key" });
		} finally {
			busy = false;
		}
	}

	async function revoke(label: string) {
		if (busy) return;
		busy = true;
		try {
			await api.deleteDebugKey();
			if (!alive) return;
			created = null;
			dialog = null;
			toasts.push({ kind: "info", message: label });
			await load();
		} catch {
			toasts.push({ kind: "error", message: "Could not revoke the key" });
		} finally {
			busy = false;
		}
	}

	function selectKey() {
		if (!keyBox) return;
		const r = document.createRange();
		r.selectNodeContents(keyBox);
		const s = window.getSelection();
		s?.removeAllRanges();
		s?.addRange(r);
	}

	async function copy() {
		if (!created) return;
		try {
			await navigator.clipboard.writeText(created.key);
			copied = true;
			toasts.push({ kind: "info", message: "Copied" });
			clearTimeout(copiedTimer);
			copiedTimer = setTimeout(() => (copied = false), 2000);
		} catch {
			// Clipboard blocked: leave the key selected so it can be copied by hand.
			selectKey();
			toasts.push({ kind: "error", message: "Could not copy. Copy the key by hand." });
		}
	}

	function openDialog() {
		opener = document.activeElement as HTMLElement | null;
		dialog = "pick";
		void tick().then(() => dialogEl?.focus());
	}

	function closeDialog() {
		if (dialog === "shown") created = null;
		dialog = null;
		opener?.focus();
	}

	function onDialogKeydown(e: KeyboardEvent) {
		// The key is shown once: only Done closes that step.
		if (e.key === "Escape" && dialog === "pick") {
			e.preventDefault();
			closeDialog();
		}
	}

	onMount(() => {
		void load();
	});
</script>

<section class="card debugkey">
	<div class="head">
		<h2 class="card-title">
			<Icon name="shield" size={18} />
			Debug access
			{#if phase === "ready" && status?.state === "expired"}
				<span class="chip"><Icon name="triangle-alert" size={14} />Expired</span>
			{/if}
		</h2>
		{#if phase === "ready" && status}
			<button class="btn pri" disabled={busy} onclick={openDialog}>
				{status.state === "off" ? "Create key" : "New key"}
			</button>
		{/if}
	</div>

	{#if phase === "loading" && !status}
		<div class="skel" role="status" aria-label="Loading"></div>
		<div class="skel short"></div>
	{:else if phase === "error"}
		<div class="body" role="alert">
			<p class="line nopad">Could not load the key state</p>
			<div class="btns"><button class="btn" onclick={load}>Retry</button></div>
		</div>
	{:else if status && status.state !== "off"}
		{@const expired = status.state === "expired"}
		<p class="line" aria-live="polite">
			{expired ? "This key no longer works." : "On. Claude can read jobs, logs and state."}
		</p>
		<div class="body">
			<dl>
				<div>
					<dt>Key id</dt>
					<dd>{status.id}</dd>
				</div>
				<div>
					<dt>{expired ? "Expired" : "Expires"}</dt>
					<dd title={exact(status.expires_at)} aria-label={exact(status.expires_at)}>
						{rel(status.expires_at, true)}
					</dd>
				</div>
				<div>
					<dt>Last used</dt>
					<dd>{status.last_used_at ? `${rel(status.last_used_at, false)} (approx.)` : "never"}</dd>
				</div>
				<div>
					<dt>Uses</dt>
					<dd>about {status.uses_approx}</dd>
				</div>
			</dl>
			{#if !expired && !status.expires_at}
				<p class="warn"><Icon name="triangle-alert" size={16} />No expiry. Revoke the key when you are done.</p>
			{/if}
			<div class="btns">
				<button
					class="btn dng"
					disabled={busy}
					onclick={() => revoke(expired ? "Key removed" : "Key revoked")}
				>
					<Icon name="trash" size={18} />{expired ? "Remove" : "Revoke"}
				</button>
			</div>
		</div>
	{/if}
</section>

{#if dialog}
	<div
		class="overlay"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget && dialog === "pick") closeDialog();
		}}
	>
		<div
			class="dlg"
			role="dialog"
			tabindex="-1"
			aria-modal="true"
			aria-labelledby="debugkey-dlg-title"
			bind:this={dialogEl}
			onkeydown={onDialogKeydown}
		>
			{#if dialog === "shown" && created}
				<h2 class="card-title" id="debugkey-dlg-title">
					<Icon name="shield" size={18} />Key created
				</h2>
				<p class="line" aria-live="polite">{created.expires_at ? `Expires ${rel(created.expires_at, true)}.` : "It never expires."}</p>
				<div class="body">
					<div class="keywrap">
						<div
							class="key"
							bind:this={keyBox}
							role="textbox"
							tabindex="0"
							aria-readonly="true"
							aria-label="Debug key, shown once"
							onclick={selectKey}
							onkeydown={(e) => (e.key === "Enter" ? selectKey() : null)}
						>{created.key}</div>
						<button class="icb" aria-label="Copy key" title="Copy key" onclick={copy}>
							<Icon name={copied ? "check" : "copy"} size={18} />
						</button>
					</div>
					<p class="warn"><Icon name="triangle-alert" size={16} />Shown once. Store it now; Pearlie keeps only a hash.</p>
					<div class="btns">
						<button class="btn pri" onclick={closeDialog}>Done</button>
					</div>
				</div>
			{:else}
				<h2 class="card-title" id="debugkey-dlg-title">
					{status?.state === "off" ? "Create key" : "Replace the current key?"}
				</h2>
				<div class="body">
					<div class="seg-group" role="group" aria-label="Key lifetime">
						{#each TTLS as t (t.id)}
							<button class="seg" aria-pressed={ttl === t.id} onclick={() => (ttl = t.id)}>{t.label}</button>
						{/each}
					</div>
					<div class="btns">
						<button class="btn pri" disabled={busy} onclick={create}>
							{status?.state === "off" ? "Create key" : "Replace"}
						</button>
						<button class="btn" onclick={closeDialog}>Cancel</button>
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.card-title {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		padding-right: 16px;
	}
	.overlay {
		position: fixed;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.4);
		z-index: 1000;
	}
	.dlg {
		background: var(--surface);
		border-radius: var(--r-sm);
		padding-bottom: var(--s-4);
		max-width: 460px;
		width: calc(100% - 32px);
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
	}
	.line {
		margin: 0;
		padding: 2px 16px 8px;
		color: var(--muted);
		font-size: var(--t-13);
	}
	.line.nopad {
		padding: 0;
	}
	.body {
		padding: var(--s-1) 16px 0;
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}
	.skel {
		height: 14px;
		width: 70%;
		border-radius: 4px;
		background: var(--line);
		margin: 12px 16px 0;
	}
	.skel.short {
		width: 40%;
		margin-top: 6px;
		margin-bottom: 8px;
	}
	.seg-group {
		display: flex;
	}
	.seg {
		flex: 1;
		min-height: 44px;
		background: transparent;
		border: 1px solid var(--line-strong);
		color: var(--muted);
		font-size: var(--t-13);
		cursor: pointer;
		border-radius: 0;
	}
	.seg:first-child {
		border-radius: var(--r-sm) 0 0 var(--r-sm);
	}
	.seg:last-child {
		border-radius: 0 var(--r-sm) var(--r-sm) 0;
	}
	.seg + .seg {
		border-left: 0;
	}
	.seg[aria-pressed="true"] {
		background: var(--accent-bg);
		color: var(--accent);
		box-shadow: inset 0 -3px 0 var(--accent);
	}
	.btns {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2) var(--s-4);
	}
	.btn {
		min-height: 44px;
		min-width: 88px;
		padding: 0 var(--s-4);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--s-2);
		border: 1px solid var(--line-strong);
		background: var(--surface);
		color: var(--text);
		border-radius: var(--r-sm);
		cursor: pointer;
		font: inherit;
	}
	.btn.pri {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--on-accent);
		font-weight: 600;
	}
	.btn.dng {
		background: var(--danger-bg);
		border-color: transparent;
		color: var(--danger-fg);
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.keywrap {
		display: flex;
		gap: var(--s-2);
		align-items: stretch;
	}
	.key {
		flex: 1;
		min-width: 0;
		background: var(--bg);
		border: 1px solid var(--line-strong);
		border-radius: var(--r-sm);
		padding: var(--s-3);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: var(--t-12);
		overflow-wrap: anywhere;
		user-select: all;
	}
	.icb {
		min-width: 44px;
		min-height: 44px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 1px solid var(--line-strong);
		border-radius: var(--r-sm);
		background: var(--surface);
		color: var(--text);
		cursor: pointer;
	}
	.warn {
		display: flex;
		align-items: flex-start;
		gap: var(--s-2);
		margin: 0;
		color: var(--progress);
		font-size: var(--t-13);
	}
	dl {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: var(--s-2) var(--s-3);
	}
	dl > div {
		min-width: 0;
	}
	dt,
	dd {
		margin: 0;
	}
	dt {
		color: var(--muted);
		font-size: var(--t-12);
	}
	dd {
		font-size: var(--t-13);
		font-variant-numeric: tabular-nums;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		background: var(--danger-bg);
		color: var(--danger-fg);
		font-size: var(--t-12);
		font-weight: 400;
		border-radius: 999px;
		padding: 2px var(--s-2);
	}
</style>
