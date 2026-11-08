<script lang="ts">
	import PageImg from "./PageImg.svelte";
	import EndCard from "./EndCard.svelte";
	import { pageSrc, type Fit } from "./pages";

	let {
		count,
		page,
		template,
		fit,
		zoom,
		est,
		onsize,
		oncurrent,
		ontoggle,
		onscrolldir,
		endCard,
	}: {
		count: number;
		page: number;
		template: string;
		fit: Fit;
		zoom: number;
		est: { w: number; h: number } | null;
		onsize: (n: number, w: number, h: number) => void;
		oncurrent: (n: number) => void;
		ontoggle: () => void;
		onscrolldir: (d: "up" | "down") => void;
		endCard: {
			title: string;
			next: { title: string; thumb_url: string | null } | null;
			hasSeries: boolean;
			onnext: () => void;
			onback: () => void;
		};
	} = $props();

	let stage: HTMLDivElement;
	let vw = $state(0);
	let vh = $state(0);
	const view = $derived({ w: vw, h: vh });
	let lastCurrent = 0;
	let dirAnchor = 0;

	function onScroll() {
		const top = stage.getBoundingClientRect().top;
		const threshold = top + vh * 0.3;
		const els = stage.querySelectorAll<HTMLElement>("[data-page]");
		for (const el of els) {
			const r = el.getBoundingClientRect();
			if (r.top <= threshold && threshold < r.bottom) {
				const n = Number(el.dataset.page);
				if (n !== lastCurrent) {
					lastCurrent = n;
					oncurrent(n);
				}
				break;
			}
		}
		const delta = stage.scrollTop - dirAnchor;
		if (Math.abs(delta) > 30) {
			onscrolldir(delta > 0 ? "down" : "up");
			dirAnchor = stage.scrollTop;
		}
	}

	$effect(() => {
		const p = page;
		if (p !== lastCurrent) {
			const el = stage.querySelector<HTMLElement>(`[data-page="${p}"]`);
			el?.scrollIntoView({ behavior: "auto", block: "start" });
			lastCurrent = p;
			dirAnchor = stage.scrollTop;
		}
	});
</script>

<div class="stage" bind:this={stage} bind:clientWidth={vw} bind:clientHeight={vh} onscroll={onScroll} onclick={ontoggle}>
	<div class="col">
		{#each Array.from({ length: count }, (_, i) => i + 1) as n (n)}
			<div data-page={n}>
				<PageImg {n} src={pageSrc(template, n)} {fit} {zoom} {est} {view} across={1} {onsize} />
			</div>
		{/each}
		<EndCard title={endCard.title} next={endCard.next} hasSeries={endCard.hasSeries} onnext={endCard.onnext} onback={endCard.onback} />
	</div>
</div>

<style>
	.stage {
		position: absolute;
		inset: 0;
		overflow-y: auto;
		overflow-x: hidden;
	}

	.col {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0;
	}

	:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
