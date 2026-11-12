<script lang="ts">
	import { onDestroy, onMount } from "svelte";
	import { getApi } from "../api/client";
	import { createUpdate } from "../stores/update.svelte";
	import Icon from "../components/Icon.svelte";
	import Switch from "../components/Switch.svelte";

	const update = createUpdate(getApi());
	onMount(() => {
		void update.load(true).then(() => update.resume());
	});

	let confirming = $state(false);
	onDestroy(() => update.dispose());
	function confirm() { confirming = false; void update.apply(); }
	const updateLabel = $derived(update.status && update.status.channel !== update.status.installed.channel && update.status.available ? `Switch to ${update.latest?.version}` : "Update");
</script>

<section class="card">
	<h2>Update</h2>
	{#if update.phase === "running" || update.phase === "restarting"}
		<div class="strip" role="status">
			<span class="spin"><Icon name="refresh" size={16} /></span>
			{update.phase === "restarting" ? "Restarting…" : (update.step ?? "Starting…")}
		</div>
	{/if}
	{#if update.phase === "failed_rollback"}
		<div class="banner" role="alert">
			<p>Update failed and could not be rolled back. Run pearlie-update in the Pearlie console to repair.</p>
			{#if update.applyError}
				<p>{update.applyError}</p>
			{/if}
		</div>
	{/if}
	<ul class="rows">
		<!-- Installed -->
		<li class="row">
			<span class="row-label">Installed</span>
			<span class="row-value">
				{#if update.status}
					{update.status.installed.version}
					<span class="pill">{update.status.installed.channel}</span>
				{:else if update.offline || update.error}
					<span class="muted">Update status unavailable.</span>
				{:else}
					<span class="muted">Loading…</span>
				{/if}
			</span>
		</li>

		{#if update.status}
			<!-- Latest -->
			<li class="row">
				<span class="row-label">Latest</span>
				<span class="row-value">
					{#if update.latestState === "available"}
						{update.latest?.version}
					{:else if update.latestState === "up_to_date"}
						Up to date
					{:else if update.latestState === "check_later"}
						<span class="muted">{update.latest?.version}</span>
						<span class="muted">Check later</span>
					{:else if update.latestState === "unreachable"}
						<span class="muted">{update.latest?.version}</span>
						<span class="muted">Unreachable</span>
					{:else}
						—
					{/if}
				</span>
			</li>

			<!-- Channel -->
			<li class="row">
				<span class="row-label">Channel</span>
				<span class="row-value">
					<button
						class="seg"
						aria-pressed={update.status.channel === "main"}
						disabled={update.busy || update.checking}
						onclick={() => update.setChannel("main")}
					>
						Main
					</button>
					<button
						class="seg"
						aria-pressed={update.status.channel === "dev"}
						disabled={update.busy || update.checking}
						onclick={() => update.setChannel("dev")}
					>
						Dev
					</button>
				</span>
			</li>

			<!-- Auto-check -->
			<li class="row">
				<span class="row-label">Check for updates automatically</span>
				<span class="row-value">
					<Switch
						checked={update.status.check_enabled}
						label="Check for updates automatically"
						onclick={() => update.setCheckEnabled(!update.status?.check_enabled)}
					/>
				</span>
			</li>

			<!-- Actions -->
			<li class="row">
				<span class="row-value actions">
					<button
						class="iconbtn"
						class:spin={update.checking}
						aria-label="Check for updates"
						title="Check for updates"
						disabled={update.checking}
						onclick={() => update.checkNow()}
					>
						<Icon name="refresh" />
					</button>
					<button
						class="iconbtn"
						aria-label={updateLabel}
						title={update.status && !update.status.can_apply ? "Updating is not available here" : "Update"}
						disabled={!update.status?.available || !update.status?.can_apply || update.phase !== "idle"}
						onclick={() => (confirming = true)}
					>
						<Icon name="download" />
						<span class="btn-label">{updateLabel}</span>
					</button>
					{#if update.latest?.url}
						<a
							href={update.latest.url}
							target="_blank"
							rel="noopener noreferrer"
							aria-label="Release page"
							class="iconbtn"
						>
							<Icon name="external-link" />
						</a>
					{/if}
				</span>
			</li>
		{/if}
	</ul>
</section>
<svelte:window onkeydown={(e) => { if (confirming && e.key === "Escape") confirming = false; }} />
	{#if confirming}
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div class="scrim" role="presentation" onclick={() => (confirming = false)}>
			<div class="sheet" role="dialog" aria-modal="true" aria-label="Confirm update" tabindex="-1" onclick={(e) => e.stopPropagation()}>
				<p>Pearlie restarts for about a minute. Your settings and library are not changed.</p>
				<div class="sheet-actions">
					<button class="sheetbtn" onclick={() => (confirming = false)}>Cancel</button>
					<button class="sheetbtn primary" onclick={confirm}>Confirm</button>
				</div>
			</div>
		</div>
	{/if}

<style>
	.card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--r-md);
		padding: var(--s-3);
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		min-height: 44px;
		padding: var(--s-1) 0;
	}

	.row-label {
		font-size: var(--t-13);
		color: var(--text);
	}

	.row-value {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}

	.actions {
		gap: var(--s-1);
	}

	.pill {
		background: var(--accent-bg);
		color: var(--accent);
		font-size: var(--t-12);
		border-radius: 999px;
		padding: 2px var(--s-1);
	}

	.muted {
		color: var(--muted);
	}

	.seg {
		background: var(--surface);
		border: 1px solid var(--line-strong);
		color: var(--text);
		border-radius: var(--r-sm);
		min-width: 44px;
		min-height: 44px;
		padding: 0 var(--s-2);
		font-size: var(--t-13);
		cursor: pointer;
	}

	.seg:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.iconbtn {
		background: var(--surface);
		border: 1px solid var(--line-strong);
		color: var(--text);
		border-radius: var(--r-sm);
		min-width: 44px;
		min-height: 44px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		text-decoration: none;
	}

	.iconbtn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.spin {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	.btn-label {
		font-size: var(--t-13);
	}

	.strip {
		display: flex;
		flex-direction: row;
		gap: var(--s-2);
		align-items: center;
		min-height: 44px;
		color: var(--muted);
		font-size: var(--t-13);
	}
	.banner {
		border: 1px solid var(--accent);
		background: var(--accent-bg);
		border-radius: var(--r-sm);
		padding: var(--s-2);
		font-size: var(--t-13);
		margin-bottom: var(--s-2);
	}
	.scrim {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: flex-end;
		justify-content: center;
		z-index: 100;
	}
	.sheet {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--r-md) var(--r-md) 0 0;
		padding: var(--s-3);
		width: 100%;
		max-width: 480px;
		font-size: var(--t-13);
	}
	.sheet-actions {
		display: flex;
		gap: var(--s-2);
		justify-content: flex-end;
	}
	.sheetbtn {
		min-height: 44px;
		min-width: 88px;
		border: 1px solid var(--line-strong);
		background: var(--surface);
		color: var(--text);
		border-radius: var(--r-sm);
		cursor: pointer;
	}
	.sheetbtn.primary {
		background: var(--accent);
		color: var(--surface);
	}
	@media (max-width: 640px) {
		.row {
			flex-wrap: wrap;
		}
	}
</style>
