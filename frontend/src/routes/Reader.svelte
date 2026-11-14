<script lang="ts">
	import { onMount, onDestroy, untrack } from "svelte";
	import { getApi } from "../lib/api/client";
	import type { LibraryItem, WebItem } from "../lib/api/client";
	import { createSearch } from "../lib/stores/search.svelte";
	import { placement } from "../lib/stores/placement.svelte";
	import { toasts } from "../lib/stores/toasts.svelte";
	import { saveWebItem, saveStateFor, savedHrefFor } from "../lib/web/saveFlow";
	import type { SaveSlot } from "../lib/reader/saveSlot";
	import { komgaSource, webSource, type ReaderSource } from "../lib/reader/source";
	import { getRouter } from "../lib/ctx";
	import type { Match } from "../lib/router";
	import Stage from "../lib/reader/Stage.svelte";
	import ScrollStage from "../lib/reader/ScrollStage.svelte";
	import EndCard from "../lib/reader/EndCard.svelte";
	import Controls from "../lib/reader/Controls.svelte";
	import { createAutoHide, createMoveGuard, keyShowsChrome } from "../lib/reader/autohide";
	import { createProgress } from "../lib/reader/progress";
	import { loadSettings, saveSettings, type Settings } from "../lib/reader/settings";
	import {
		clampPage,
		bookStart,
		defaultMode,
		buildGroups,
		groupOf,
		stepGroup,
		keyAction,
		zoomStep,
		type Mode,
		type Fit,
		type Dir,
		type KeyAction,
	} from "../lib/reader/pages";

	let { match }: { match: Match } = $props();

	const api = getApi();
	const router = getRouter();

	const routeKey = $derived(
		match.name === "read-web" ? "web:" + match.params.source + ":" + match.params.id : "komga:" + match.params.bookId,
	);
	const seriesId = $derived(match.query.get("series"));

	function buildSource(): ReaderSource {
		return match.name === "read-web"
			? webSource(api, match.params.source, match.params.id, match.query)
			: komgaSource(api, match.params.bookId, match.query);
	}

	// source is rebuilt in load(); bookId is the progress key of the current source
	let source: ReaderSource = buildSource();
	let bookId = $state(source.key);

	// ── state ──────────────────────────────────────────────────────────
	let status = $state<"loading" | "ready" | "error">("loading");
	let title = $state("");
	let count = $state(0);
	let page = $state(1);
	let tpl = $state("");
	let thumbTpl = $state<string | null>(null);
	let books = $state<LibraryItem[]>([]);
	let notice = $state<string | null>(null);
	let saveItem = $state<WebItem | null>(null);
	const searchStore = createSearch(api);
	const saveSlot = $derived<SaveSlot | undefined>(
		saveItem
			? {
					state: saveStateFor(saveItem, searchStore.saveStateOf(saveItem)),
					href: savedHrefFor(saveItem, searchStore.saveStateOf(saveItem)),
					disabled: saveItem.saveable === false,
					onsave: () => {
						const it = saveItem;
						if (!it) return;
						void saveWebItem(
							{ ask: (i) => placement.ask(i), save: (i, p) => searchStore.save(i, p), toast: (t) => toasts.push(t) },
							it,
						);
					},
				}
			: undefined,
	);
	let wide = $state<Set<number>>(new Set<number>());
	let est = $state<{ w: number; h: number } | null>(null);
	let atEnd = $state(false);
	let popover = $state<null | "settings" | "books" | "help">(null);
	let thumbsOpen = $state(false);
	let hidden = $state(false);
	let fullscreen = $state(false);
	let toast = $state("");
	let settings = $state<Settings>({ mode: null, fit: "both", dir: "ltr", zoom: 100 });

	// ── derived ────────────────────────────────────────────────────────
	const mode = $derived<Mode>(settings.mode ?? defaultMode());
	const groups = $derived(buildGroups(count, mode, wide));
	const shown = $derived(groupOf(groups, page));
	const idx = $derived(books.findIndex((b) => b.id === bookId));
	const nextBook = $derived(idx >= 0 && idx < books.length - 1 ? books[idx + 1] : null);
	const endCard = $derived({
		title,
		next: nextBook,
		hasSeries: books.length > 0,
		onnext: openNext,
		onback: back,
	});

	// ── progress + autohide ────────────────────────────────────────────
	const progress = createProgress(async (_id, pg, o) => source.saveProgress(pg, count, o));
	const hide = createAutoHide({
		blocked: () => popover !== null || thumbsOpen,
		onchange: (v) => (hidden = v),
	});

	// ── helpers ────────────────────────────────────────────────────────
	function show(t: string) {
		toast = t;
		setTimeout(() => {
			if (toast === t) toast = "";
		}, 1500);
	}

	function setSettings(patch: Partial<Settings>) {
		settings = { ...settings, ...patch };
		saveSettings(settings);
	}

	const FITS: Fit[] = ["width", "height", "both", "actual"];
	const MODES: Mode[] = ["single", "spread", "scroll"];

	function setModeValue(m: Mode) {
		setSettings({ mode: m });
	}

	function setFitValue(f: Fit) {
		setSettings({ fit: f });
	}

	function setDirValue(d: Dir) {
		setSettings({ dir: d });
	}

	function setZoomValue(z: number) {
		setSettings({ zoom: z });
	}

	// ── loading ────────────────────────────────────────────────────────
	async function load() {
		progress.flush();
		source = buildSource();
		bookId = source.key;
		status = "loading";
		atEnd = false;
		wide = new Set<number>();
		est = null;
		thumbsOpen = false;
		popover = null;
		books = [];
		notice = null;
		saveItem = null;
		setSettings({ zoom: 100 });

		try {
			const d = await source.load();
			title = d.title;
			count = d.count;
			tpl = d.tpl;
			thumbTpl = d.thumbTpl;
			books = d.books;
			notice = d.notice;
			saveItem = d.save?.item ?? null;
			page = clampPage(d.start, count);
			status = "ready";
		} catch {
			status = "error";
		}
	}

	$effect(() => {
		void routeKey;
		untrack(() => void load());
	});

	// ── navigation ─────────────────────────────────────────────────────
	function onsize(n: number, w: number, h: number) {
		if (!est) est = { w, h };
		if (w > h && !wide.has(n)) wide = new Set([...wide, n]);
	}

	function go(n: number) {
		page = clampPage(n, count);
		atEnd = false;
		const g = groupOf(groups, page);
		progress.set(bookId, g[g.length - 1]);
		const qs = "?p=" + page + (seriesId ? "&series=" + seriesId : "");
		const base = source.kind === "web"
			? "/read/web/" + encodeURIComponent(match.params.source) + "/" + encodeURIComponent(match.params.id)
			: "/read/" + encodeURIComponent(bookId);
		router.navigate(base + qs, { replace: true });
	}

	function turn(d: 1 | -1) {
		if (atEnd) {
			if (d === 1) {
				openNext();
			} else {
				atEnd = false;
			}
			return;
		}

		const r = stepGroup(groups, page, d);
		if (typeof r === "number") {
			go(r);
		} else if (r === "end") {
			atEnd = true;
			progress.set(bookId, count);
		}
	}

	function openBook(b: LibraryItem) {
		if (b.id === bookId) { popover = null; return; }
		progress.flush();
		const start = bookStart(b);
		router.navigate("/read/" + encodeURIComponent(b.id) + "?p=" + start + "&series=" + (seriesId ?? ""), { replace: true });
		show(b.title);
	}

	function openNext() {
		if (nextBook) openBook(nextBook);
	}

	function back() {
		if (router.canGoBack()) {
			history.back();
			return;
		}
		router.navigate(source.backTarget(), { replace: true });
	}

	function toggleFullscreen() {
		if (document.fullscreenElement) {
			void document.exitFullscreen();
		} else {
			void document.documentElement.requestFullscreen();
		}
	}

	function togglePopover(p: "settings" | "books" | "help") {
		popover = popover === p ? null : p;
		hide.poke();
	}

	function onKey(e: KeyboardEvent) {
		const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
		if (tag === "input" || tag === "textarea" || tag === "select") return;

		const a: KeyAction | null = keyAction(e, settings.dir);
		if (keyShowsChrome(a)) hide.poke();

		const stage = document.querySelector(".stage");

		if (a === "next") turn(1);
		else if (a === "prev") turn(-1);
		else if (a === "first") go(1);
		else if (a === "last") go(count);
		else if (a === "book-prev" && idx > 0) openBook(books[idx - 1]);
		else if (a === "book-next") openNext();
		else if (a === "books") togglePopover("books");
		else if (a === "settings") togglePopover("settings");
		else if (a === "help") togglePopover("help");
		else if (a === "fit") {
			setFitValue(FITS[(FITS.indexOf(settings.fit) + 1) % FITS.length]);
		} else if (a === "mode") {
			setModeValue(MODES[(MODES.indexOf(mode) + 1) % MODES.length]);
		} else if (a === "mode-single") setModeValue("single");
		else if (a === "mode-spread") setModeValue("spread");
		else if (a === "mode-scroll") setModeValue("scroll");
		else if (a === "fullscreen") toggleFullscreen();
		else if (a === "thumbs") thumbsOpen = !thumbsOpen;
		else if (a === "zoom-in") setZoomValue(zoomStep(settings.zoom, 1));
		else if (a === "zoom-out") setZoomValue(zoomStep(settings.zoom, -1));
		else if (a === "zoom-reset") setZoomValue(100);
		else if (a === "hide") hide.toggle();
		else if (a === "dir") setDirValue(settings.dir === "ltr" ? "rtl" : "ltr");
		else if (a === "scroll-up" && stage) (stage as HTMLElement).scrollBy({ top: -90 });
		else if (a === "scroll-down" && stage) (stage as HTMLElement).scrollBy({ top: 90 });
		else if (a === "escape") {
			if (popover) popover = null;
			else if (thumbsOpen) thumbsOpen = false;
			else back();
		} else {
			return;
		}
		e.preventDefault();
	}

	const realMove = createMoveGuard();

	function onPointer(e: PointerEvent) {
		if (realMove(e)) hide.poke();
	}

	function onFsChange() {
		fullscreen = document.fullscreenElement != null;
	}

	// ── lifecycle ──────────────────────────────────────────────────────
	onMount(() => {
		settings = loadSettings();
		hide.poke();
		window.addEventListener("keydown", onKey);
		window.addEventListener("pointermove", onPointer);
		window.addEventListener("pagehide", () => progress.flush(true));
		document.addEventListener("fullscreenchange", onFsChange);
	});

	onDestroy(() => {
		progress.flush();
		hide.destroy();
		window.removeEventListener("keydown", onKey);
		window.removeEventListener("pointermove", onPointer);
		document.removeEventListener("fullscreenchange", onFsChange);
	});
</script>

<div class="reader" role="application" aria-label="Reader">
	{#if status === "loading"}
		<div class="center">
			<div class="skeleton"></div>
		</div>
	{:else if status === "error"}
		<div class="center">
			<p class="msg">Could not open this book.</p>
			<div class="row">
				<button class="btn" onclick={() => load()}>Retry</button>
				<button class="btn ghost" onclick={back}>Back</button>
			</div>
		</div>
	{:else}
		{#if count === 0}
			<div class="center">
				<p class="msg">This book has no pages.</p>
				<button class="btn ghost" onclick={back}>Back</button>
			</div>
		{:else if mode === "scroll"}
			<ScrollStage
				count={count}
				page={page}
				template={tpl}
				fit={settings.fit}
				zoom={settings.zoom}
				est={est}
				onsize={onsize}
				oncurrent={(n) => go(n)}
				ontoggle={() => hide.toggle()}
				onscrolldir={(d) => { if (d === "down") hide.hide(); }}
				endCard={endCard}
			/>
		{:else if atEnd}
			<div class="end">
				<EndCard
					title={title}
					next={nextBook}
					hasSeries={books.length > 0}
					onnext={openNext}
					onback={back}
				/>
			</div>
		{:else}
			<Stage
				shown={shown}
				groups={groups}
				page={page}
				template={tpl}
				fit={settings.fit}
				zoom={settings.zoom}
				dir={settings.dir}
				est={est}
				onsize={onsize}
				onturn={turn}
				ontoggle={() => hide.toggle()}
				onzoomstep={(d) => setZoomValue(zoomStep(settings.zoom, d))}
			/>
		{/if}

		<Controls
			hidden={hidden}
			popover={popover}
			thumbsOpen={thumbsOpen}
			fullscreen={fullscreen}
			mode={mode}
			fit={settings.fit}
			dir={settings.dir}
			zoom={settings.zoom}
			count={count}
			shown={shown}
			thumbTpl={thumbTpl}
			wide={wide}
			title={title}
			index={idx + 1}
			total={books.length}
			hasSeries={books.length > 0}
			books={books}
			bookId={bookId}
			notice={notice}
			onback={back}
			onsettings={() => togglePopover("settings")}
			onfit={() => setFitValue(FITS[(FITS.indexOf(settings.fit) + 1) % FITS.length])}
			onmode={() => setModeValue(MODES[(MODES.indexOf(mode) + 1) % MODES.length])}
			onfullscreen={toggleFullscreen}
			onhelp={() => togglePopover("help")}
			onprev={() => turn(-1)}
			onnext={() => turn(1)}
			onlist={() => togglePopover("books")}
			onjump={(n) => go(n)}
			onthumbs={() => (thumbsOpen = !thumbsOpen)}
			onzoomin={() => setZoomValue(zoomStep(settings.zoom, 1))}
			onzoomout={() => setZoomValue(zoomStep(settings.zoom, -1))}
			onzoomreset={() => setZoomValue(100)}
			onsetmode={setModeValue}
			onsetfit={setFitValue}
			onsetdir={setDirValue}
			onpick={(b) => openBook(b)}
			onclosepopover={() => (popover = null)}
			onhover={(v) => hide.setHover(v)}
			onfocus={(v) => hide.setFocus(v)}
			save={saveSlot}
		/>

		<div class="sr-only" aria-live="polite">Page {page} of {count}</div>
	{/if}

	{#if toast}
		<div class="toast" role="status">{toast}</div>
	{/if}
</div>

<style>
	.reader {
		position: fixed;
		inset: 0;
		z-index: 1000;
		background: #000;
		color: var(--text);
	}

	.center {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--s-4);
		padding: var(--s-4);
		text-align: center;
	}

	.skeleton {
		width: min(70vw, 640px);
		aspect-ratio: 16 / 9;
		background: var(--surface);
		border-radius: var(--r-md);
		animation: pulse 1.4s ease-in-out infinite alternate;
	}

	.msg {
		margin: 0;
		color: var(--muted);
		font-size: 15px;
	}

	.row {
		display: flex;
		gap: var(--s-2);
	}

	.btn {
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--s-3);
		border: 1px solid var(--line-strong);
		background: var(--surface);
		color: var(--text);
		border-radius: var(--r-md);
		font: inherit;
		cursor: pointer;
	}

	.btn.ghost {
		background: transparent;
	}

	.btn:hover:not(:disabled) {
		background: var(--line);
	}

	.btn.ghost:hover:not(:disabled) {
		background: var(--line);
	}

	.end {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--s-4);
	}

	.toast {
		position: absolute;
		left: var(--s-4);
		bottom: var(--s-4);
		background: var(--surface);
		border: 1px solid var(--line-strong);
		border-radius: var(--r-md);
		padding: 8px 14px;
		color: var(--text);
		font-size: 14px;
		z-index: 20;
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

	@keyframes pulse {
		from { opacity: 0.4; }
		to { opacity: 0.7; }
	}

	:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	@media (prefers-reduced-motion: reduce) {
		.skeleton {
			animation: none;
			opacity: 0.5;
		}
	}
</style>
