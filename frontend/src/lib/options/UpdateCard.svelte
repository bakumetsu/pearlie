<script lang="ts">
	import { onDestroy, onMount } from "svelte";
	import { getApi } from "../api/client";
	import { createUpdate } from "../stores/update.svelte";
	import { getRouter } from "../ctx";
	import { linkClick } from "../router";
	import Icon from "../components/Icon.svelte";
	import Switch from "../components/Switch.svelte";

	let router: ReturnType<typeof getRouter> | null = null;
	try { router = getRouter(); } catch { /* no router context: the link does a normal page load */ }
	const update = createUpdate(getApi());
	onMount(() => {
		void update.load(true).then(() => update.resume());
	});

	let confirming = $state(false);
	let sheet: "restart" | "rollback" | null = $state(null);
	let restoreDb = $state(false);
	onDestroy(() => update.dispose());
	function confirm() { confirming = false; void update.apply(); }
	function closeSheets() { confirming = false; sheet = null; }
	function openSheet(kind: "restart" | "rollback") { restoreDb = false; sheet = kind; }
	function runSheet() {
		const kind = sheet;
		const force = jobs > 0;
		const restore = restoreDb;
		sheet = null;
		if (kind === "restart") void update.restart(force);
		else if (kind === "rollback") void update.rollback({ restoreDb: restore, force });
	}
	const rb = $derived(update.status?.rollback ?? null);
	const canRestart = $derived(!!update.status?.can_restart);
	const jobs = $derived(update.status?.jobs_running ?? 0);
	const plural = (n: number) => `${n} ${n === 1 ? "job is" : "jobs are"} running`;
	const askRestore = $derived(!!rb && rb.schema !== "same" && !!rb.backup_at);
	function when(iso: string | null | undefined): string {
		if (!iso) return "";
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return iso;
		const p = (n: number) => String(n).padStart(2, "0");
		return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
	}
	const actionOff = $derived(update.phase !== "idle" || update.busy || update.checking);
	const updateLabel = $derived(
		update.status && update.status.channel !== update.status.installed.channel && update.status.available
			? `Switch to ${update.latest?.version}`
			: update.status?.available && update.latest?.version
				? `Update to ${update.latest.version}`
				: "Update",
	);
</script>

<section class="card">
	<h2>Update</h2>
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
					<span title={update.status.installed.commit ? update.status.installed.commit.slice(0, 7) : undefined}>{update.status.installed.version}</span>
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
		{/if}

		<!-- Actions -->
		<li class="row">
			<span class="row-value actions">
				{#if update.status}
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
						title={update.status && !update.status.can_apply ? "Updating is not available here" : updateLabel}
						disabled={!update.status?.available || !update.status?.can_apply || update.phase !== "idle"}
						onclick={() => (confirming = true)}
					>
						<Icon name="download" />
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
					<span class="sep"></span>
					<button
						class="iconbtn"
						aria-label={rb ? `Roll back to ${rb.version}` : "Roll back"}
						title={rb ? `Roll back to ${rb.version}` : "No earlier version is kept"}
						disabled={!rb || !canRestart || actionOff}
						onclick={() => openSheet("rollback")}
					>
						<Icon name="rotate-ccw" />
					</button>
					<button
						class="iconbtn"
						aria-label="Restart server"
						title={canRestart ? "Restart server" : "Restarting is not available here"}
						disabled={!canRestart || actionOff}
						onclick={() => openSheet("restart")}
					>
						<Icon name="power" />
					</button>
				{:else if update.offline || update.error}
					<button class="iconbtn" aria-label="Retry" title="Retry" onclick={() => update.retry()}>
						<Icon name="refresh" />
					</button>
				{/if}
				{#if update.phase === "running" || update.phase === "restarting"}
					<div class="strip" role="status">
						<span class="spin"><Icon name="refresh" size={16} /></span>
						{update.phase === "restarting" ? "Restarting…" : (update.step ?? "Starting…")}
					</div>
				{/if}
			</span>
		</li>
	</ul>
	{#if update.status}
		{#if canRestart && !rb}
			<p class="muted">Roll back is off: no earlier version is kept.</p>
		{/if}
		{#if update.note}
			<p class="muted" role="status">{update.note}</p>
		{/if}
		<a class="cl-link" href="/options/changelog" onclick={(e) => { if (router) linkClick(e, router); }}>
			<Icon name="history" size={18} />
			{update.status.available ? "See what's new" : "See changelog"}
		</a>
	{/if}
</section>

<svelte:window onkeydown={(e) => { if ((confirming || sheet) && e.key === "Escape") closeSheets(); }} />
{#if confirming}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div class="scrim" role="presentation" onclick={closeSheets}>
		<div class="sheet" role="dialog" aria-modal="true" aria-label="Confirm update" tabindex="-1" onclick={(e) => e.stopPropagation()}>
			<p>Pearlie restarts for about a minute. Your settings and library are not changed.</p>
			<div class="sheet-actions">
				<button class="sheetbtn" onclick={closeSheets}>Cancel</button>
				<button class="sheetbtn primary" onclick={confirm}>Confirm</button>
			</div>
		</div>
	</div>
{/if}
{#if sheet}
	{@const heading = sheet === "restart" ? "Restart server" : `Roll back to ${rb?.version ?? ""}`}
	{@const restoring = sheet === "rollback" && askRestore && restoreDb}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div class="scrim" role="presentation" onclick={closeSheets}>
		<div class="sheet" role="dialog" aria-modal="true" aria-label={heading} tabindex="-1" onclick={(e) => e.stopPropagation()}>
			<h3>{heading}</h3>
			{#if jobs > 0}
				<p class="jobs">{plural(jobs)}. They go back to the queue and restart from the beginning.</p>
			{/if}
			{#if sheet === "restart"}
				<p>Pearlie restarts for about a minute.{jobs > 0 ? "" : " Running jobs restart from the beginning."}</p>
			{:else}
				<p>Go back to {rb?.version}. {rb?.schema === "same" ? "Your database and library are not changed. " : ""}Pearlie restarts for about a minute.</p>
				{#if rb && rb.schema !== "same"}
					<p>The database layout may have changed since {rb.version}. If Pearlie does not start, restore the backup.</p>
				{/if}
				{#if askRestore}
					<label class="check">
						<input type="checkbox" bind:checked={restoreDb} />
						<span>Also restore the database backup from {when(rb?.backup_at)} (loses changes since the update)</span>
					</label>
				{/if}
			{/if}
			<div class="sheet-actions">
				<button class="sheetbtn" onclick={closeSheets}>Cancel</button>
				<button class="sheetbtn primary" class:warn={restoring} onclick={runSheet}>
					{#if sheet === "restart"}
						{jobs > 0 ? "Restart anyway" : "Restart"}
					{:else if restoring}
						Roll back and restore
					{:else}
						{jobs > 0 ? "Roll back anyway" : "Roll back"}
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.row-value {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}

	.actions {
		gap: var(--s-1);
		width: 100%;
	}

	.actions .strip {
		margin-left: auto;
	}

	.cl-link {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		min-height: 44px;
		color: var(--accent);
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
		background: transparent;
		border: 1px solid var(--line-strong);
		color: var(--muted);
		border-radius: 0;
		min-width: 44px;
		min-height: 44px;
		padding: 0 var(--s-2);
		font-size: var(--t-13);
		cursor: pointer;
	}

	.seg[aria-pressed="true"] {
		background: var(--accent-bg);
		color: var(--accent);
	}

	.seg:first-of-type {
		border-radius: var(--r-sm) 0 0 var(--r-sm);
	}

	.seg:last-of-type {
		border-radius: 0 var(--r-sm) var(--r-sm) 0;
		border-left: 0;
	}

	.seg:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.iconbtn {
		background: transparent;
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
	.sheetbtn.warn {
		background: var(--danger-bg);
		color: var(--danger-fg);
		border-color: var(--danger-hot);
	}
	.sheet h3 {
		margin: 0 0 var(--s-2);
		font-size: var(--t-15);
	}
	.jobs {
		color: var(--danger-fg);
	}
	.check {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-height: 44px;
		margin-bottom: var(--s-2);
	}
	.check input {
		width: 22px;
		height: 22px;
		flex: none;
	}
	.sep {
		display: inline-block;
		width: 12px;
		flex: none;
	}
	@media (max-width: 640px) {
		.row {
			flex-wrap: wrap;
		}
	}
</style>
