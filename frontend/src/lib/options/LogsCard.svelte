<script lang="ts">
	import { onDestroy, onMount } from "svelte";
	import { errorText, getApi } from "../api/client";
	import type { LogFileInfo, LogLevel, LogLine } from "../api/client";
	import Icon from "../components/Icon.svelte";
	import type { IconName } from "../components/Icon.svelte";
	import Switch from "../components/Switch.svelte";
	import { toasts } from "../stores/toasts.svelte";

	const api = getApi();

	const LEVELS: { id: LogLevel; label: string; icon: IconName }[] = [
		{ id: "error", label: "Error", icon: "octagon-x" },
		{ id: "warning", label: "Warning", icon: "triangle-alert" },
		{ id: "info", label: "Info", icon: "info" },
		{ id: "debug", label: "Debug", icon: "bug" },
	];
	const LONG = 100;

	let debug = $state(false);
	let debugBusy = $state(false);
	let keepDays = $state(7);
	let dirName = $state("logs");
	let files = $state<LogFileInfo[]>([]);
	let date = $state("");
	let level = $state<LogLevel>("info");
	let lines = $state<LogLine[]>([]);
	let cursor = $state<string | null>(null);
	let phase = $state<"loading" | "ready" | "error">("loading");
	let more = $state(false);
	let moreFailed = $state(false);
	let expanded = $state<number[]>([]);

	let seq = 0;
	let alive = true;
	onDestroy(() => {
		alive = false;
	});

	function size(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
	}

	function time(ts: string): string {
		return ts.slice(11, 19);
	}

	function asText(l: LogLine): string {
		return l.ts ? `${l.ts} ${l.level.toUpperCase()}  ${l.logger}  ${l.text}` : l.text;
	}

	async function loadFirst(refreshFiles: boolean) {
		const mine = ++seq;
		phase = "loading";
		more = false;
		moreFailed = false;
		try {
			if (refreshFiles) {
				const info = await api.getLogs();
				if (!alive || mine !== seq) return;
				debug = info.debug;
				keepDays = info.keep_days;
				dirName = info.dir_name;
				files = info.files;
				if (!files.some((f) => f.date === date)) date = files[0]?.date ?? "";
			}
			if (!date) {
				lines = [];
				cursor = null;
				expanded = [];
				phase = "ready";
				return;
			}
			const page = await api.getLogLines(date, { level, limit: 200 });
			if (!alive || mine !== seq) return;
			lines = page.lines;
			cursor = page.next_cursor;
			expanded = [];
			phase = "ready";
		} catch {
			if (!alive || mine !== seq) return;
			phase = "error";
		}
	}

	async function loadOlder() {
		if (!cursor || more) return;
		const mine = seq;
		more = true;
		moreFailed = false;
		try {
			const page = await api.getLogLines(date, { level, cursor, limit: 200 });
			if (!alive || mine !== seq) return;
			lines = [...lines, ...page.lines];
			cursor = page.next_cursor;
		} catch {
			if (!alive || mine !== seq) return;
			moreFailed = true;
		} finally {
			more = false;
		}
	}

	async function toggleDebug() {
		if (debugBusy) return;
		const next = !debug;
		debugBusy = true;
		debug = next;
		try {
			const r = await api.putLogDebug(next);
			debug = r.debug;
		} catch (e) {
			debug = !next;
			toasts.push({ kind: "error", message: errorText(e) });
		} finally {
			debugBusy = false;
		}
	}

	function pickDate(e: Event) {
		date = (e.currentTarget as HTMLSelectElement).value;
		void loadFirst(false);
	}

	function pickLevel(l: LogLevel) {
		if (l === level) return;
		level = l;
		void loadFirst(false);
	}

	async function copy() {
		try {
			await navigator.clipboard.writeText(lines.map(asText).join("\n"));
			toasts.push({ kind: "info", message: "Copied" });
		} catch {
			toasts.push({ kind: "error", message: "Could not copy" });
		}
	}

	function toggle(i: number) {
		expanded = expanded.includes(i) ? expanded.filter((x) => x !== i) : [...expanded, i];
	}

	onMount(() => {
		void loadFirst(true);
	});
</script>

<section class="card">
	<h2 class="card-title">Logging</h2>
	<div class="row">
		<span class="row-label">
			Debug
			<span class="hint">Adds detail. Off by default. Turn off when done.</span>
		</span>
		<span class="row-value">
			{#if debug}<span class="pill">Debug is on</span>{/if}
			<Switch checked={debug} label="Debug" disabled={debugBusy} onclick={toggleDebug} />
		</span>
	</div>
	<div class="row">
		<span class="row-label">Kept</span>
		<span class="row-value muted">{keepDays} days, one file per day (data/{dirName})</span>
	</div>
</section>

<section class="card viewer">
	<h2 class="card-title">Log viewer</h2>
	<div class="toolbar">
		<select
			class="day"
			aria-label="Day"
			title="Day"
			value={date}
			disabled={files.length === 0}
			onchange={pickDate}
		>
			{#each files as f (f.date)}
				<option value={f.date}>{f.date} · {f.lines} lines · {size(f.size_bytes)}</option>
			{/each}
		</select>
		<div class="seg-group" role="group" aria-label="Level">
			{#each LEVELS as l (l.id)}
				<button
					class="seg"
					aria-label={l.label}
					title={l.label}
					aria-pressed={level === l.id}
					onclick={() => pickLevel(l.id)}
				>
					<Icon name={l.icon} size={18} />
				</button>
			{/each}
		</div>
		<div class="actions">
			<button
				class="iconbtn"
				class:spin={phase === "loading"}
				aria-label="Refresh"
				title="Refresh"
				onclick={() => loadFirst(true)}
			>
				<Icon name="refresh" size={18} />
			</button>
			<button
				class="iconbtn"
				aria-label="Copy"
				title="Copy"
				disabled={lines.length === 0}
				onclick={copy}
			>
				<Icon name="copy" size={18} />
			</button>
			{#if date}
				<a
					class="iconbtn"
					aria-label="Download"
					title="Download"
					href={api.logDownloadUrl(date, level)}
					download={`pearlie-${date}.log`}
				>
					<Icon name="download" size={18} />
				</a>
			{:else}
				<span class="iconbtn disabled" aria-label="Download" role="img" title="Download">
					<Icon name="download" size={18} />
				</span>
			{/if}
		</div>
	</div>

	<div class="body">
		{#if phase === "loading" && lines.length === 0}
			<p class="state" role="status">Loading…</p>
		{:else if phase === "error"}
			<div class="state" role="alert">
				<p>Could not load the log</p>
				<button class="textbtn" onclick={() => loadFirst(true)}>Retry</button>
			</div>
		{:else if lines.length === 0}
			<p class="state">
				{files.length === 0 ? "No logs yet." : "No lines at this level for this day."}
			</p>
		{:else}
			<ol class="lines" aria-label="Log lines">
				{#each lines as l, i (i)}
					{@const long = l.text.length > LONG}
					<li class="line {l.level}" class:cont={!l.ts}>
						{#snippet content()}
							{#if l.ts}
								<span class="ts">{time(l.ts)}</span>
								<span class="tag"><Icon name={LEVELS.find((x) => x.id === l.level)?.icon ?? "info"} size={14} />{l.level}</span>
							{/if}
							<span class="text" class:clamp={long && !expanded.includes(i)}>{l.text}</span>
						{/snippet}
						{#if long}
							<button class="linebtn" aria-expanded={expanded.includes(i)} onclick={() => toggle(i)}>
								{@render content()}
							</button>
						{:else}
							<div class="linebtn plain">{@render content()}</div>
						{/if}
					</li>
				{/each}
			</ol>
			{#if cursor}
				<div class="older">
					{#if moreFailed}<span class="muted">Could not load older lines.</span>{/if}
					<button class="textbtn" disabled={more} onclick={loadOlder}>
						{more ? "Loading…" : "Load older"}
					</button>
				</div>
			{/if}
		{/if}
	</div>
</section>

<style>
	.row-label {
		display: flex;
		flex-direction: column;
	}
	.row-value {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.muted {
		color: var(--muted);
		font-size: var(--t-13);
	}
	.pill {
		background: var(--accent-bg);
		color: var(--accent);
		font-size: var(--t-12);
		border-radius: 999px;
		padding: 2px var(--s-1);
	}

	.toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-2);
		margin-bottom: var(--s-2);
	}
	.day {
		min-height: 44px;
		min-width: 0;
		flex: 1 1 220px;
		background: var(--surface);
		color: var(--text);
		border: 1px solid var(--line-strong);
		border-radius: var(--r-sm);
		padding: 0 var(--s-2);
		font-size: var(--t-13);
	}
	.seg-group {
		display: inline-flex;
	}
	.seg {
		background: transparent;
		border: 1px solid var(--line-strong);
		color: var(--muted);
		min-width: 44px;
		min-height: 44px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
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
	.actions {
		display: inline-flex;
		gap: var(--s-1);
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
	.iconbtn:disabled,
	.iconbtn.disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.spin :global(svg) {
		animation: spin 1s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.body {
		max-height: 60vh;
		overflow: auto;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
	}
	.state {
		margin: 0;
		padding: var(--s-3);
		color: var(--muted);
		font-size: var(--t-13);
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-1);
	}
	.state p {
		margin: 0;
	}
	.lines {
		list-style: none;
		margin: 0;
		padding: 0;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: var(--t-12);
	}
	.line {
		border-left: 3px solid transparent;
		border-bottom: 1px solid var(--line);
	}
	.line.error {
		border-left-color: var(--accent);
		border-left-width: 5px;
	}
	.line.warning {
		border-left-color: var(--line-strong);
	}
	.linebtn {
		display: flex;
		align-items: baseline;
		gap: var(--s-2);
		width: 100%;
		box-sizing: border-box;
		text-align: left;
		background: transparent;
		border: 0;
		color: var(--text);
		font: inherit;
		padding: var(--s-1) var(--s-2);
	}
	button.linebtn {
		min-height: 44px;
		cursor: pointer;
	}
	.line.cont .linebtn {
		padding-left: var(--s-4, 24px);
		color: var(--muted);
	}
	.ts {
		color: var(--muted);
		flex: none;
	}
	.tag {
		flex: none;
		display: inline-flex;
		align-items: center;
		gap: 2px;
		min-width: 76px;
		text-transform: uppercase;
	}
	.text {
		flex: 1;
		min-width: 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.text.clamp {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.older {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--s-2);
		padding: var(--s-1);
	}
	.textbtn {
		min-height: 44px;
		min-width: 88px;
		border: 1px solid var(--line-strong);
		background: var(--surface);
		color: var(--text);
		border-radius: var(--r-sm);
		cursor: pointer;
		padding: 0 var(--s-2);
	}
	.textbtn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
