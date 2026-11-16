<script lang="ts">
	import { getApi, ApiError } from "../api/client";
	import type { Api, TrashFolder } from "../api/client";
	import Icon from "../components/Icon.svelte";

	let { api = getApi() }: { api?: Api } = $props();

	let folder = $state<TrashFolder | null>(null);
	let draft = $state("");
	let error = $state("");
	// The last Save answered folder_missing: Create makes the typed path.
	let missingTyped = $state(false);
	let busy = $state(false);

	const MESSAGES: Record<string, string> = {
		trash_not_empty: "Restore or delete the items in the Trash first",
		invalid_path: "Enter an absolute folder path",
		folder_missing: "Folder does not exist. Create it, then save",
		not_writable: "Folder is not writable",
		inside_library: "Folder is inside a Stash or Komga library",
		other_volume: "Folder is not on the same drive as the Stash library",
		stash_root_unreachable: "A Stash library folder cannot be reached, so the drive check failed",
		upstream_error: "Stash or Komga could not be reached",
		cannot_create: "Could not create the folder",
	};

	function messageOf(e: unknown): string {
		if (e instanceof ApiError) return MESSAGES[e.code] ?? e.message;
		return "Request failed";
	}

	$effect(() => {
		const ctl = new AbortController();
		Promise.resolve().then(() => api.trashFolder(ctl.signal)).then(
			(f) => { folder = f; draft = f.path; },
			() => {},
		);
		return () => ctl.abort();
	});

	const locked = $derived((folder?.items ?? 0) > 0);
	const showCreate = $derived(
		folder !== null && !locked && (missingTyped || (folder.state === "missing" && draft === folder.path)),
	);
	const statusText = $derived(
		folder === null
			? "Loading…"
			: locked
				? `Locked: ${folder.items} item${folder.items === 1 ? "" : "s"} in the Trash`
				: folder.state === "ok"
					? "OK"
					: folder.state === "missing"
						? "Folder is missing"
						: "Folder is not writable",
	);
	const sourceText = $derived(folder?.source === "env" ? "default" : "set here");

	async function save() {
		busy = true;
		error = "";
		try {
			const f = await api.setTrashFolder(draft.trim());
			folder = f;
			draft = f.path;
			missingTyped = false;
		} catch (e) {
			error = messageOf(e);
			missingTyped = e instanceof ApiError && e.code === "folder_missing";
		} finally {
			busy = false;
		}
	}

	async function create() {
		busy = true;
		error = "";
		try {
			const typed = draft.trim();
			const f = await api.createTrashFolder(typed === folder?.path ? "" : typed);
			folder = typed === "" || typed === f.path ? f : folder;
			missingTyped = false;
			if (typed !== "" && typed !== f.path) error = "Folder created. Save to use it";
		} catch (e) {
			error = messageOf(e);
		} finally {
			busy = false;
		}
	}
</script>

<section class="card">
	<h2 class="card-title">Trash folder</h2>
	<div class="row controls">
		<input
			type="text"
			data-testid="trash-folder-path"
			aria-label="Trash folder path"
			placeholder={folder?.env_path ?? ""}
			bind:value={draft}
			disabled={folder === null || locked}
		/>
		{#if folder !== null && !locked}
			<button type="button" class="icon-btn" data-testid="trash-folder-save" aria-label="Save trash folder" disabled={busy} onclick={save}>
				<Icon name="check" />
			</button>
		{/if}
		{#if showCreate}
			<button type="button" class="icon-btn" data-testid="trash-folder-create" aria-label="Create folder" disabled={busy} onclick={create}>
				<Icon name="plus" />
			</button>
		{/if}
	</div>
	<p class="hint" data-testid="trash-folder-status">{statusText}{folder && !locked ? ` · ${sourceText}` : ""}</p>
	{#if error}<span class="err" role="alert" data-testid="trash-folder-error">{error}</span>{/if}
</section>

<style>
	.controls {
		flex-wrap: wrap;
	}
	input {
		flex: 1 1 14rem;
		min-height: 44px;
	}
	.icon-btn {
		min-height: 44px;
		min-width: 44px;
		border: 1px solid var(--line-strong);
		border-radius: 4px;
		background: transparent;
		color: inherit;
		cursor: pointer;
	}
</style>
