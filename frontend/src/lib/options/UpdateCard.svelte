<script lang="ts">
	import { onMount } from "svelte";
	import { getApi } from "../api/client";
	import { createUpdate } from "../stores/update.svelte";
	import Icon from "../components/Icon.svelte";
	import Switch from "../components/Switch.svelte";

	const update = createUpdate(getApi());
	onMount(() => {
		void update.load(true);
	});

	let { onupdate }: { onupdate?: () => void } = $props();
	const updateLabel = $derived(update.status && update.status.channel !== update.status.installed.channel && update.status.available ? `Switch to ${update.latest?.version}` : "Update");
</script>

<section class="card">
	<h2>Update</h2>
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
				<span class="row-value">
					<span class="row-label">Check for updates automatically</span>
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
						disabled={!update.status?.available || !update.status?.can_apply}
						onclick={() => onupdate?.()}
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

	@media (max-width: 640px) {
		.row {
			flex-wrap: wrap;
		}
	}
</style>
