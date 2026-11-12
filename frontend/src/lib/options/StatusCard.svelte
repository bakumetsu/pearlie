<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { getApi, type Health } from "../api/client";

	const api = getApi();
	let health = $state<Health | null>(null);
	let healthError = $state<string | null>(null);
	let controller = new AbortController();

	onMount(() => {
		api.health(controller.signal)
			.then((h) => {
				health = h;
			})
			.catch((e) => {
				if (!controller.signal.aborted) healthError = String(e);
			});
	});

	onDestroy(() => {
		controller.abort();
	});

	function chipClass(state: string): string {
		if (state === "ok") return "ok";
		if (state === "down") return "down";
		return "neutral";
	}

	function statusLabel(state: string): string {
		if (state === "ok") return "OK";
		if (state === "down") return "Down";
		if (state === "not_configured") return "Not configured";
		return state;
	}
</script>

<section class="card">
	<h2 class="card-title">Status</h2>
	{#if health}
		<ul class="statusrows">
			<li class="row"><span>Stash</span><span class="chip {chipClass(health.stash.state)}">{statusLabel(health.stash.state)}</span></li>
			<li class="row"><span>Komga</span><span class="chip {chipClass(health.komga.state)}">{statusLabel(health.komga.state)}</span></li>
			<li class="row"><span>Database</span><span class="chip {chipClass(health.db === "ok" ? "ok" : "down")}">{statusLabel(health.db === "ok" ? "ok" : "down")}</span></li>
			{#each health.mounts as mount, i (i)}
				<li class="row"><span>Mount {mount.name}</span><span class="chip {chipClass(mount.state)}">{statusLabel(mount.state)}</span></li>
			{/each}
			{#each health.sites as site, i (i)}
				<li class="row"><span>{site.id}</span><span class="chip {chipClass(site.state)}">{statusLabel(site.state)}</span></li>
			{/each}
		</ul>
	{:else if healthError}
		<p class="hint">Status unavailable.</p>
	{/if}
</section>

<style>
	.statusrows {
		list-style: none;
		margin: 0;
		padding: 0;
	}
</style>
