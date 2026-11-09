<script lang="ts">
	import { fitScale, type Fit } from "./pages";
	type Props = {
		n: number; src: string; fit: Fit; zoom: number;
		view: { w: number; h: number }; across: 1 | 2;
		est: { w: number; h: number } | null;
		onsize: (n: number, w: number, h: number) => void; onfail?: (n: number) => void;
	};
	let { n, src, fit, zoom, view, across, est, onsize, onfail }: Props = $props();
	let nat = $state<{ w: number; h: number } | null>(null);
	let failed = $state(false);
	let bust = $state(0);
	const size = $derived.by(() => {
		const p = nat ?? est ?? { w: 1000, h: 1500 };
		const s = fitScale(fit, zoom, view, p, across);
		return { width: p.w * s, height: p.h * s };
	});
	const imgSrc = $derived(bust ? src + (src.includes("?") ? "&" : "?") + "r=" + bust : src);
</script>

<div class="tile" style:width={size.width + "px"} style:height={size.height + "px"}>
	{#if failed}
		<button class="retry" onclick={(e) => { e.stopPropagation(); failed = false; bust += 1; }}>Retry page {n}</button>
	{:else}
		<img src={imgSrc} alt={"Page " + n} draggable="false"
			onload={(e) => { const i = e.currentTarget as HTMLImageElement; nat = { w: i.naturalWidth, h: i.naturalHeight }; onsize(n, i.naturalWidth, i.naturalHeight); }}
			onerror={() => { failed = true; onfail?.(n); }} />
	{/if}
	{#if !failed && !nat}<span class="ph">{n}</span>{/if}
</div>

<style>
	.tile{position:relative;flex:none;display:flex;align-items:center;justify-content:center;overflow:hidden;background:#1b1b1f}
	.tile img{position:absolute;inset:0;width:100%;height:100%;object-fit:fill;display:block}
	.ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text);opacity:.55;font-variant-numeric:tabular-nums}
	.retry{min-width:44px;min-height:44px;padding:0 12px;border:1px solid var(--line-strong);border-radius:6px;background:transparent;color:var(--text);font:inherit;cursor:pointer}
	:focus-visible{outline:2px solid var(--accent)}
</style>
