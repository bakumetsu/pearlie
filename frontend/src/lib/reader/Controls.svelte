<script lang="ts">
	import Rail from "./Rail.svelte";
	import BookPill from "./BookPill.svelte";
	import BookList from "./BookList.svelte";
	import BottomCard from "./BottomCard.svelte";
	import ThumbStrip from "./ThumbStrip.svelte";
	import ZoomPill from "./ZoomPill.svelte";
	import SettingsPopover from "./SettingsPopover.svelte";
	import HelpSheet from "./HelpSheet.svelte";

	import type { Mode, Fit, Dir } from "./pages";
	import type { LibraryItem } from "../api/client";

	type Props = {
		hidden: boolean;
		popover: null | "settings" | "books" | "help";
		thumbsOpen: boolean;
		fullscreen: boolean;
		mode: Mode;
		fit: Fit;
		dir: Dir;
		zoom: number;
		count: number;
		shown: number[];
		thumbTpl: string | null;
		wide?: Set<number>;
		title: string;
		index: number;
		total: number;
		hasSeries: boolean;
		books: LibraryItem[];
		bookId: string;
		notice: string | null;
		onback: () => void;
		onsettings: () => void;
		onfit: () => void;
		onmode: () => void;
		onfullscreen: () => void;
		onhelp: () => void;
		onprev: () => void;
		onnext: () => void;
		onlist: () => void;
		onjump: (n: number) => void;
		onthumbs: () => void;
		onzoomin: () => void;
		onzoomout: () => void;
		onzoomreset: () => void;
		onsetmode: (m: Mode) => void;
		onsetfit: (f: Fit) => void;
		onsetdir: (d: Dir) => void;
		onpick: (book: LibraryItem) => void;
		onclosepopover: () => void;
		onhover: (v: boolean) => void;
		onfocus: (v: boolean) => void;
	};

	let {
		hidden,
		popover,
		thumbsOpen,
		fullscreen,
		mode,
		fit,
		dir,
		zoom,
		count,
		shown,
		thumbTpl,
		wide = new Set<number>(),
		title,
		index,
		total,
		hasSeries,
		books,
		bookId,
		notice,
		onback,
		onsettings,
		onfit,
		onmode,
		onfullscreen,
		onhelp,
		onprev,
		onnext,
		onlist,
		onjump,
		onthumbs,
		onzoomin,
		onzoomout,
		onzoomreset,
		onsetmode,
		onsetfit,
		onsetdir,
		onpick,
		onclosepopover,
		onhover,
		onfocus,
	}: Props = $props();
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="controls"
	class:hidden
	inert={hidden}
	onpointerenter={() => onhover(true)}
	onpointerleave={() => onhover(false)}
	onfocusin={() => onfocus(true)}
	onfocusout={() => onfocus(false)}
>
	<BookPill {title} {index} {total} {hasSeries} {onprev} {onnext} {onlist} />
	<Rail {fit} {mode} {fullscreen} settingsOpen={popover === "settings"} {onback} {onsettings} {onfit} {onmode} {onfullscreen} {onhelp} />
	<BottomCard {count} {shown} {dir} {thumbsOpen} {onjump} {onthumbs} />
	<ZoomPill {zoom} onin={onzoomin} onout={onzoomout} onreset={onzoomreset} />
	{#if thumbsOpen}
		<ThumbStrip {count} {shown} template={thumbTpl} {wide} {onjump} />
	{/if}
	{#if popover === "books"}
		<BookList {books} currentId={bookId} {notice} {onpick} onclose={onclosepopover} />
	{/if}
	{#if popover === "settings"}
		<SettingsPopover {mode} {fit} {dir} onmode={onsetmode} onfit={onsetfit} ondir={onsetdir} onclose={onclosepopover} />
	{/if}
	{#if popover === "help"}
		<HelpSheet onclose={onclosepopover} />
	{/if}
</div>

<style>
	.controls { position: absolute; inset: 0; pointer-events: none; transition: opacity 200ms; container-type: inline-size; }
	.controls > :global(*) { pointer-events: auto; }
	.hidden { opacity: 0; }
	@media (prefers-reduced-motion: reduce) { .controls { transition: none; } }
</style>
