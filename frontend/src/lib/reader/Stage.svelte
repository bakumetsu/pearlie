<script lang="ts">
	import PageImg from "./PageImg.svelte";
	import {
		zoneAction,
		shouldWheelTurn,
		pageSrc,
		preloadPages,
		displayOrder,
		slideFrom,
		type Dir,
		type Fit,
	} from "./pages";

	let {
		shown,
		groups,
		page,
		template,
		fit,
		zoom,
		dir,
		est,
		onsize,
		onturn,
		ontoggle,
		onzoom,
		onzoomstep,
	}: {
		shown: number[];
		groups: number[][];
		page: number;
		template: string;
		fit: Fit;
		zoom: number;
		dir: Dir;
		est: { w: number; h: number } | null;
		onsize: (n: number, w: number, h: number) => void;
		onturn: (delta: 1 | -1) => void;
		ontoggle: () => void;
		onzoom: (z: number) => void;
		onzoomstep: (d: 1 | -1) => void;
	} = $props();

	let stageEl = $state<HTMLDivElement | null>(null);
	let width = $state(0);
	let height = $state(0);
	let lastTurn = $state(0);
	let prevPage = -1;
	let from = $state<"left" | "right" | null>(null);
	$effect.pre(() => {
		const p = page;
		const side = slideFrom(prevPage, p, groups, dir);
		prevPage = p;
		from =
			side && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
				? side
				: null;
	});

	const view = $derived({ w: width, h: height });
	const order = $derived(displayOrder(shown, dir));
	const across = $derived<1 | 2>(shown.length >= 2 ? 2 : 1);
	const preloads = $derived(preloadPages(groups, page));

	function handleStageClick(e: MouseEvent) {
		const el = stageEl;
		if (!el) return;
		const rect = el.getBoundingClientRect();
		const action = zoneAction(e.clientX - rect.left, rect.width, dir);
		if (action === "next") onturn(1);
		else if (action === "prev") onturn(-1);
		else ontoggle();
	}

	function handleStageDblClick(e: MouseEvent) {
		const el = stageEl;
		if (!el) return;
		const rect = el.getBoundingClientRect();
		const action = zoneAction(e.clientX - rect.left, rect.width, dir);
		if (action === "toggle") {
			onzoom(zoom === 100 ? 200 : 100);
		}
	}

	function handleWheel(e: WheelEvent) {
		if (e.ctrlKey) {
			e.preventDefault();
			onzoomstep(e.deltaY < 0 ? 1 : -1);
			return;
		}
		const el = stageEl;
		if (!el) return;
		const atEnd = e.deltaY > 0
			? el.scrollTop + el.clientHeight >= el.scrollHeight - 1
			: el.scrollTop <= 0;
		if (atEnd && shouldWheelTurn(e.deltaY, performance.now(), lastTurn)) {
			lastTurn = performance.now();
			onturn(e.deltaY > 0 ? 1 : -1);
		}
	}
</script>

<div
	class="stage"
	role="presentation"
	bind:this={stageEl}
	bind:clientWidth={width}
	bind:clientHeight={height}
	onclick={handleStageClick}
	ondblclick={handleStageDblClick}
	onwheel={handleWheel}
>
	{#key page}
		<div class="row" data-from={from} style:--slide="{Math.round(width * 0.18)}px">
			{#each order as n (n)}
				<PageImg
					{n}
					src={pageSrc(template, n)}
					{fit}
					{zoom}
					{est}
					{view}
					{across}
					{onsize}
				/>
			{/each}
		</div>
	{/key}
	{#each preloads as n (n)}
		<img class="preload" src={pageSrc(template, n)} alt="" aria-hidden="true" />
	{/each}
</div>

<style>
	.stage {
		position: absolute;
		inset: 0;
		overflow: auto;
		display: flex;
		background: #000;
		color: var(--text);
		scrollbar-width: thin;
		scrollbar-color: var(--line-strong) transparent;
	}

	.row {
		margin: auto;
		display: flex;
		flex: none;
		align-items: center;
		justify-content: center;
	}

	.row[data-from] {
		animation: slide-in 180ms ease-out both;
	}

	.row[data-from="left"] {
		--dx: calc(var(--slide) * -1);
	}

	.row[data-from="right"] {
		--dx: var(--slide);
	}

	@keyframes slide-in {
		from {
			transform: translateX(var(--dx));
			opacity: 0.4;
		}
		to {
			transform: translateX(0);
			opacity: 1;
		}
	}

	.preload {
		display: none;
	}

	:focus-visible {
		outline: 2px solid var(--accent);
	}

	@media (prefers-reduced-motion: reduce) {
		.stage {
			scroll-behavior: auto;
		}
		.row {
			animation: none;
		}
	}
</style>
