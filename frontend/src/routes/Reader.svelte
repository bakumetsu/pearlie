<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { getApi } from "../lib/api/client";
	import { getRouter } from "../lib/ctx";
	import type { Match } from "../lib/router";
	import Icon from "../lib/components/Icon.svelte";
	import {
		clampPage,
		visiblePages,
		nextPage,
		prevPage,
		stepKey,
		zoneAction,
		preloadPages,
		isCompleted,
		parseMode,
		DEFAULT_MODE,
		type ReadMode
	} from "../lib/reader/pages";
	import type { LibraryItem } from "../lib/api/client";

	let { match }: { match: Match } = $props();

	const api = getApi();
	const router = getRouter();
	const bookId = $derived(match.params.bookId);

	// ── state ──────────────────────────────────────────────────────────
	let title = $state("");
	let count = $state(0);
	let page = $state(1);
	let status = $state<"loading" | "ready" | "error">("loading");
	let mode = $state<ReadMode>({ ...DEFAULT_MODE });
	let chrome = $state(true);
	let nextBook = $state<LibraryItem | null>(null);
	let failed = $state<Set<number>>(new Set());
	let wide = $state(false);
	let width = $state(0);
	let bust = $state(0);

	// ── derived ────────────────────────────────────────────────────────
	const series = $derived(match.query.get("series"));
	const spread = $derived(mode.spread && wide);
	const shown = $derived(visiblePages(page, count, spread));
	const pagesToShow = $derived(mode.rtl ? [...shown].reverse() : shown);
	const pre = $derived(preloadPages(page, count, spread));

	// ── mode persistence ───────────────────────────────────────────────
	const MODE_KEY = "pearlie.reader.mode";

	function saveMode() {
		try {
			localStorage.setItem(MODE_KEY, JSON.stringify(mode));
		} catch {}
	}

	// ── load ───────────────────────────────────────────────────────────
	async function load() {
		status = "loading";
		try {
			const d = await api.getItem("books", bookId);
			title = d.title;
			count = d.page_count ?? 0;
			const p = Number(match.query.get("p"));
			const start = match.query.get("p") ? p : (d.read_page ?? 1);
			page = clampPage(start, count);
			status = "ready";
		} catch {
			status = "error";
		}

		const seriesId = match.query.get("series");
		if (seriesId) {
			try {
				const s = await api.getItem("series", seriesId);
				const books: LibraryItem[] = s.books ?? [];
				const idx = books.findIndex((b) => b.id === bookId);
				nextBook = idx >= 0 && idx < books.length - 1 ? books[idx + 1] : null;
			} catch {
				// ignore
			}
		}
	}

	// ── navigation ─────────────────────────────────────────────────────
	function go(n: number) {
		page = clampPage(n, count);
		scheduleProgress();
		const qs = "?p=" + page + (series ? "&series=" + series : "");
		router.navigate("/read/" + encodeURIComponent(bookId) + qs, { replace: true });
	}

	function next() {
		const n = nextPage(page, count, spread);
		if (n !== null) go(n);
		// else: end tile handled in markup when nextBook is set
	}

	function prev() {
		go(prevPage(page, count, spread));
	}

	// ── progress ───────────────────────────────────────────────────────
	let progressTimer: ReturnType<typeof setTimeout> | null = null;

	function scheduleProgress() {
		if (progressTimer) clearTimeout(progressTimer);
		progressTimer = setTimeout(() => {
			progressTimer = null;
			try {
				const lastShownPage = shown[shown.length - 1];
				api.saveProgress(bookId, lastShownPage);
			} catch {}
		}, 800);
	}

	function flushProgress() {
		if (progressTimer) {
			clearTimeout(progressTimer);
			progressTimer = null;
		}
		try {
			const lastShownPage = shown[shown.length - 1];
			fetch(
				"/api/library/komga/books/" + encodeURIComponent(bookId) + "/progress",
				{
					method: "POST",
					keepalive: true,
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ page: lastShownPage })
				}
			);
		} catch {}
	}

	// ── chrome auto-hide ───────────────────────────────────────────────
	let chromeTimer: ReturnType<typeof setTimeout> | null = null;

	function poke() {
		chrome = true;
		if (chromeTimer) clearTimeout(chromeTimer);
		chromeTimer = setTimeout(() => {
			chrome = false;
			chromeTimer = null;
		}, 3000);
	}

	// ── keyboard ───────────────────────────────────────────────────────
	function onKey(e: KeyboardEvent) {
		poke();
		if (e.key === "Escape") {
			router.navigate("/item/books/" + encodeURIComponent(bookId));
			return;
		}
		const a = stepKey(e.key, mode.rtl);
		if (a === "next") next();
		else if (a === "prev") prev();
		else if (a === "first") go(1);
		else if (a === "last") go(count);
	}

	// ── stage click ────────────────────────────────────────────────────
	function onStageClick(e: MouseEvent) {
		const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
		const act = zoneAction(e.clientX - r.left, r.width, mode.rtl);
		if (act === "next") next();
		else if (act === "prev") prev();
		else if (act === "toggle") chrome = !chrome;
	}

	// ── mode toggles ───────────────────────────────────────────────────
	function toggleSpread() {
		mode = { ...mode, spread: !mode.spread };
		saveMode();
	}

	function toggleRtl() {
		mode = { ...mode, rtl: !mode.rtl };
		saveMode();
	}

	function toggleFit() {
		mode = { ...mode, fit: mode.fit === "height" ? "width" : "height" };
		saveMode();
	}

	// ── retry ──────────────────────────────────────────────────────────
	function retryPage(n: number) {
		const s = new Set(failed);
		s.delete(n);
		failed = s;
		bust = bust + 1;
	}

	// ── page url ───────────────────────────────────────────────────────
	function pageUrl(n: number) {
		return api.pageUrl(bookId, n);
	}

	// ── lifecycle ──────────────────────────────────────────────────────
	onMount(() => {
		// restore mode
		try {
			mode = parseMode(localStorage.getItem(MODE_KEY));
		} catch {}

		// wide
		wide = window.innerWidth >= 900;
		function onResize() {
			wide = window.innerWidth >= 900;
		}
		window.addEventListener("resize", onResize);

		// chrome
		poke();

		// listeners
		window.addEventListener("mousemove", poke);
		window.addEventListener("keydown", onKey);
		window.addEventListener("pagehide", flushProgress);

		onDestroy(() => {
			if (chromeTimer) clearTimeout(chromeTimer);
			window.removeEventListener("resize", onResize);
			window.removeEventListener("mousemove", poke);
			window.removeEventListener("keydown", onKey);
			window.removeEventListener("pagehide", flushProgress);
			flushProgress();
		});
	});

	// reload when bookId changes
	$effect(() => {
		const id = bookId;
		failed = new Set();
		nextBook = null;
		page = 1;
		void load();
	});
</script>
<div class="reader" role="application" aria-label="Reader">
	{#if status === "loading"}
		<div class="loading">
			<div class="skeleton"></div>
		</div>
	{:else if status === "error"}
		<div class="error">
			<p>Could not open this book.</p>
			<button onclick={() => load()}>Retry</button>
			<a href="/item/books/{bookId}">Back</a>
		</div>
	{:else}
		<header class="bar top" class:hidden={!chrome}>
			<button aria-label="Back to book" onclick={() => router.navigate("/item/books/" + bookId)}>
				<Icon name="arrow-left" size={24} />
			</button>
			<span class="title">{title}</span>
			<span class="page-indicator">{page} / {count}</span>
			{#if wide}
				<button
					aria-label="Two-page spread"
					aria-pressed={spread}
					class:pressed={spread}
					onclick={toggleSpread}
				>
					<Icon name="columns" size={24} />
				</button>
			{/if}
			<button aria-label="Right to left" aria-pressed={mode.rtl} class:pressed={mode.rtl} onclick={toggleRtl}>
				<Icon name="arrow-left-right" size={24} />
			</button>
			<button
				aria-label="Fit width"
				aria-pressed={mode.fit === "width"}
				class:pressed={mode.fit === "width"}
				onclick={toggleFit}
			>
				<Icon name="maximize" size={24} />
			</button>
		</header>

		<div class="stage" bind:clientWidth={width} onclick={onStageClick} role="presentation">
			{#each pagesToShow as n (n)}
				<div class="pg">
					{#if failed.has(n)}
						<button class="retry" onclick={(e) => { e.stopPropagation(); retryPage(n); }}>
							<Icon name="refresh" size={24} /> Retry page {n}
						</button>
					{:else}
						<img
							src={api.pageUrl(bookId, n) + "?r=" + bust}
							alt="Page {n}"
							class:fitw={mode.fit === "width"}
							onerror={() => (failed = new Set([...failed, n]))}
							draggable="false"
						/>
					{/if}
				</div>
			{/each}
			{#each pre as n (n)}
				<img class="preload" src={api.pageUrl(bookId, n)} alt="" aria-hidden="true" />
			{/each}
			{#if page === count && nextBook}
				<button
					class="nextbook"
					onclick={() => nextBook && router.navigate("/read/" + encodeURIComponent(nextBook.id) + "?series=" + series)}
				>
					Next: {nextBook.title}
				</button>
			{/if}
		</div>

		<footer class="bar bottom" class:hidden={!chrome}>
			<input
				type="range"
				min="1"
				max={Math.max(count, 1)}
				value={page}
				aria-label="Page"
				dir={mode.rtl ? "rtl" : "ltr"}
				oninput={(e) => go(Number(e.currentTarget.value))}
			/>
		</footer>

		<div class="sr-only" aria-live="polite">Page {page} of {count}</div>
	{/if}
</div>

<style>
	.reader {
		position: fixed;
		inset: 0;
		z-index: 1000;
		background: #000;
		color: var(--text);
		display: flex;
		flex-direction: column;
	}

	.loading {
		flex: 1;
		display: flex;
		justify-content: center;
		align-items: center;
	}

	.skeleton {
		width: min(70vw, 640px);
		aspect-ratio: 16 / 9;
		background: var(--surface);
		border-radius: var(--r-md);
		animation: pulse 1.4s ease-in-out infinite alternate;
	}

	@keyframes pulse {
		from { opacity: 0.4; }
		to { opacity: 0.7; }
	}

	.error {
		flex: 1;
		display: flex;
		flex-direction: column;
		justify-content: center;
		align-items: center;
		gap: var(--s-3);
		color: var(--muted);
		font-size: var(--t-14);
	}

	.error button,
	.error a {
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--s-3);
		background: transparent;
		border: 1px solid var(--line-strong);
		color: var(--text);
		border-radius: var(--r-sm);
		text-decoration: none;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}

	.stage {
		flex: 1;
		min-height: 0;
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 0;
		overflow: auto;
		cursor: pointer;
	}

	.stage:has(.pg img.fitw) {
		align-items: flex-start;
	}

	.pg {
		display: flex;
		height: 100%;
		align-items: center;
	}

	.pg img {
		max-height: 100%;
		max-width: 100%;
		object-fit: contain;
	}

	.pg img.fitw {
		width: 100%;
		height: auto;
		max-height: none;
	}

	.bar {
		position: absolute;
		left: 0;
		right: 0;
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2) var(--s-4);
		background: rgba(18, 18, 20, 0.85);
		transition: opacity 0.2s;
	}

	.bar.top {
		top: 0;
	}

	.bar.bottom {
		bottom: 0;
	}

	.bar.hidden {
		opacity: 0;
		pointer-events: none;
	}

	.bar button {
		min-width: 44px;
		min-height: 44px;
		background: transparent;
		border: 1px solid var(--line-strong);
		color: var(--text);
		border-radius: var(--r-sm);
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}

	.bar button[aria-pressed="true"] {
		background: var(--accent-bg);
	}

	.title {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		flex: 1;
		font-size: var(--t-14);
	}

	.page-indicator {
		font-size: var(--t-13);
		color: var(--muted);
		white-space: nowrap;
	}

	.bar input[type="range"] {
		flex: 1;
	}

	.preload {
		position: absolute;
		width: 1px;
		height: 1px;
		opacity: 0;
		pointer-events: none;
	}

	.retry {
		height: 44px;
		min-height: 44px;
		color: var(--muted);
		background: transparent;
		border: 1px solid var(--line-strong);
		border-radius: var(--r-sm);
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		padding: 0 var(--s-3);
	}

	.nextbook {
		position: absolute;
		bottom: 72px;
		left: 50%;
		transform: translateX(-50%);
		min-height: 44px;
		padding: 0 var(--s-4);
		background: var(--accent);
		color: #0b1220;
		border: 0;
		border-radius: var(--r-md);
		font-size: var(--t-14);
	}

	:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	@media (prefers-reduced-motion: reduce) {
		.bar {
			transition: none;
		}

		.skeleton {
			animation: none;
			opacity: 0.5;
		}
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
</style>
